from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime, date, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..database import async_session
from ..models.standup_note import StandupNote
from ..models.standup import StandupSummary
from ..models.user import User, Team
from ..models.sprint import Sprint
from ..services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class StandupAgent:
    """Agent responsible for coordinating daily standups"""

    def __init__(self):
        self.llm_provider = LLMProvider()

    def get_system_prompt(self) -> str:
        return """You are a Standup Coordination Agent for an Agile/Scrum team. Your role is to:

1. Analyze standup notes from team members
2. Generate clear, actionable standup summaries
3. Identify blockers and risks
4. Suggest follow-up actions
5. Highlight patterns and concerns

Format your summaries with clear sections:
- COMPLETED YESTERDAY: What was accomplished
- PLANNED TODAY: What team members will work on
- BLOCKERS: Issues preventing progress
- NOTES: Additional observations, risks, or suggestions

Be concise but thorough. Focus on actionable information."""

    async def execute(self, team_id: int, target_date: Optional[date] = None, db_session = None) -> Dict[str, Any]:
        """Execute standup coordination workflow

        Args:
            team_id: ID of the team
            target_date: Date to generate standup for (defaults to today)
            db_session: Optional database session (creates one if not provided)

        Returns:
            Dict containing summary and metadata
        """

        if not target_date:
            target_date = datetime.now().date()

        logger.info(f"Running standup for team {team_id} on {target_date}")

        # Use provided session or create a new one
        if db_session:
            return await self._execute_with_session(db_session, team_id, target_date)
        else:
            async with async_session() as session:
                return await self._execute_with_session(session, team_id, target_date)

    async def _execute_with_session(self, session, team_id: int, target_date: date) -> Dict[str, Any]:
        """Execute with provided session"""
        try:
            # Step 1: Fetch standup notes from database
            standup_notes = await self._fetch_standup_notes(session, team_id, target_date)

            if not standup_notes:
                logger.warning(f"No standup notes found for team {team_id} on {target_date}")
                return {
                    "success": False,
                    "error": "No standup notes found for this date",
                    "date": target_date.isoformat(),
                    "team_id": team_id
                }

            # Step 2: Format prompt for LLM
            prompt = await self._format_prompt_for_llm(session, standup_notes, team_id, target_date)

            # Step 3: Call LLM to generate summary
            llm_response = await self._call_llm(prompt)

            # Step 4: Parse LLM response
            parsed_data = self._parse_llm_response(llm_response)

            # Step 5: Save summary to database
            summary = await self._save_summary(
                session,
                team_id,
                target_date,
                parsed_data,
                standup_notes
            )

            return {
                "success": True,
                "summary_id": summary.id,
                "date": target_date.isoformat(),
                "team_id": team_id,
                "summary_text": parsed_data["summary_text"],
                "completed_yesterday": parsed_data["completed_yesterday"],
                "planned_today": parsed_data["planned_today"],
                "blockers": parsed_data["blockers"],
                "action_items": parsed_data["action_items"],
                "risk_indicators": parsed_data["risk_indicators"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "tokens_used": llm_response.get("tokens_used", 0),
                "cost_usd": llm_response.get("cost_usd", 0.0)
            }

        except Exception as e:
            logger.error(f"Standup execution error: {str(e)}", exc_info=True)
            raise

    async def _fetch_standup_notes(self, session, team_id: int, target_date: date) -> List[StandupNote]:
        """Fetch standup notes for a specific team and date from database"""

        stmt = select(StandupNote).where(
            StandupNote.team_id == team_id,
            StandupNote.date == target_date
        ).options(selectinload(StandupNote.user))

        result = await session.execute(stmt)
        notes = result.scalars().all()

        logger.info(f"Found {len(notes)} standup notes for team {team_id} on {target_date}")
        return list(notes)

    async def _format_prompt_for_llm(
        self,
        session,
        standup_notes: List[StandupNote],
        team_id: int,
        target_date: date
    ) -> str:
        """Format standup notes into a coherent prompt for LLM"""

        # Get team info
        team_stmt = select(Team).where(Team.id == team_id)
        team_result = await session.execute(team_stmt)
        team = team_result.scalar_one_or_none()
        team_name = team.name if team else f"Team {team_id}"

        # Get sprint info if available
        sprint_info = ""
        if standup_notes and standup_notes[0].sprint_id:
            sprint_stmt = select(Sprint).where(Sprint.id == standup_notes[0].sprint_id)
            sprint_result = await session.execute(sprint_stmt)
            sprint = sprint_result.scalar_one_or_none()
            if sprint:
                sprint_info = f"\n**Sprint**: {sprint.name} (Goal: {sprint.goal})"

        # Format individual standup notes
        notes_text = []
        for note in standup_notes:
            user_name = note.user.full_name if note.user else "Unknown User"

            completed = "\n    - ".join(note.completed_yesterday) if note.completed_yesterday else "Nothing reported"
            planned = "\n    - ".join(note.planned_today) if note.planned_today else "Nothing planned"
            blockers = "\n    - ".join(note.blockers) if note.blockers else "No blockers"

            note_text = f"""
**{user_name}**:
  Completed Yesterday:
    - {completed}

  Planned Today:
    - {planned}

  Blockers:
    - {blockers}
"""
            if note.notes:
                note_text += f"  Additional Notes: {note.notes}\n"

            notes_text.append(note_text)

        # Construct full prompt
        prompt = f"""You are analyzing a daily standup for {team_name} on {target_date}.{sprint_info}

## Individual Standup Notes:

{''.join(notes_text)}

## Your Task:

Please generate a comprehensive standup summary following this EXACT format:

## COMPLETED YESTERDAY
[Bulleted list of what the team accomplished yesterday]

## PLANNED TODAY
[Bulleted list of what the team plans to work on today]

## BLOCKERS
[Bulleted list of blockers and impediments - if none, write "No blockers reported"]

## NOTES
[Additional observations, risks, patterns, or suggestions for the Scrum Master]

After the summary, provide a JSON object with structured data:

```json
{{
  "action_items": [
    {{"description": "action needed", "assignee": "person or team", "priority": "high|medium|low"}}
  ],
  "risk_indicators": [
    "risk 1",
    "risk 2"
  ],
  "sentiment": "positive|neutral|negative|mixed",
  "absent_members": []
}}
```

Focus on patterns, dependencies, and actionable insights."""

        return prompt

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Call LLM to generate summary using LLMProvider"""

        system_prompt = self.get_system_prompt()

        response = await self.llm_provider.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.3  # Lower temperature for more consistent output
        )

        return response

    def _parse_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and structure the LLM response"""

        content = llm_response.get("content", "")

        # Extract the main summary text (everything before JSON)
        json_start = content.find("```json")
        if json_start != -1:
            summary_text = content[:json_start].strip()
            json_end = content.find("```", json_start + 7)
            json_str = content[json_start + 7:json_end].strip()
        else:
            summary_text = content
            json_str = "{}"

        # Parse structured data from JSON
        try:
            structured_data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM response, using defaults")
            structured_data = {
                "action_items": [],
                "risk_indicators": [],
                "sentiment": "neutral",
                "absent_members": []
            }

        # Extract sections from summary text
        completed_yesterday = self._extract_section(summary_text, "COMPLETED YESTERDAY", "PLANNED TODAY")
        planned_today = self._extract_section(summary_text, "PLANNED TODAY", "BLOCKERS")
        blockers = self._extract_section(summary_text, "BLOCKERS", "NOTES")

        return {
            "summary_text": summary_text,
            "completed_yesterday": self._parse_bullet_list(completed_yesterday),
            "planned_today": self._parse_bullet_list(planned_today),
            "blockers": self._parse_bullet_list(blockers),
            "action_items": structured_data.get("action_items", []),
            "risk_indicators": structured_data.get("risk_indicators", []),
            "sentiment_score": self._sentiment_to_score(structured_data.get("sentiment", "neutral")),
            "absent_members": structured_data.get("absent_members", [])
        }

    def _extract_section(self, text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between two section markers"""
        start_idx = text.find(start_marker)
        if start_idx == -1:
            return ""

        start_idx += len(start_marker)
        end_idx = text.find(end_marker, start_idx)

        if end_idx == -1:
            section_text = text[start_idx:]
        else:
            section_text = text[start_idx:end_idx]

        return section_text.strip()

    def _parse_bullet_list(self, text: str) -> List[str]:
        """Parse bullet points from text"""
        if not text:
            return []

        lines = text.split('\n')
        bullets = []

        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('*') or line.startswith('•'):
                bullet = line[1:].strip()
                if bullet:
                    bullets.append(bullet)

        return bullets

    def _sentiment_to_score(self, sentiment: str) -> float:
        """Convert sentiment string to score"""
        sentiment_map = {
            "positive": 0.8,
            "neutral": 0.5,
            "negative": 0.2,
            "mixed": 0.5
        }
        return sentiment_map.get(sentiment.lower(), 0.5)

    async def _save_summary(
        self,
        session,
        team_id: int,
        target_date: date,
        parsed_data: Dict[str, Any],
        standup_notes: List[StandupNote]
    ) -> StandupSummary:
        """Save the generated summary to the database"""

        # Get sprint_id from first note (all notes should have same sprint)
        sprint_id = standup_notes[0].sprint_id if standup_notes else None

        # Get creator_id (use first user, or could be the Scrum Master)
        creator_id = standup_notes[0].user_id if standup_notes else None

        summary = StandupSummary(
            date=target_date,
            team_id=team_id,
            sprint_id=sprint_id,
            creator_id=creator_id,
            summary_text=parsed_data["summary_text"],
            completed_yesterday=parsed_data["completed_yesterday"],
            planned_today=parsed_data["planned_today"],
            blockers=parsed_data["blockers"],
            absent_members=parsed_data["absent_members"],
            ai_generated=True,
            sentiment_score=parsed_data["sentiment_score"],
            risk_indicators=parsed_data["risk_indicators"],
            action_items=parsed_data["action_items"],
            posted_to_slack=False,
            human_approved=False
        )

        session.add(summary)
        await session.commit()
        await session.refresh(summary)

        logger.info(f"Saved standup summary with ID {summary.id}")

        return summary
