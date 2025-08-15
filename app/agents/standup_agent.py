from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime, date, timezone
from ..services.ai_engine import AIEngine
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class StandupAgent(BaseAgent):
    """Agent responsible for coordinating daily standups"""
    
    def __init__(self, ai_engine: AIEngine):
        super().__init__(ai_engine)
    
    def get_agent_prompt(self) -> str:
        return """You are a Standup Coordination Agent. Your role is to:

1. Gather standup information from team members
2. Analyze progress on sprint tasks
3. Identify blockers and risks
4. Generate clear, actionable standup summaries
5. Suggest follow-up actions

Format your summaries with clear sections:
- COMPLETED YESTERDAY: What was accomplished
- PLANNED TODAY: What team members will work on  
- BLOCKERS: Issues preventing progress
- NOTES: Additional observations or suggestions

Be concise but thorough. Focus on actionable information."""
    
    async def execute(self, team_id: int, sprint_id: Optional[int] = None, date: date = None) -> Dict[str, Any]:
        """Execute standup coordination workflow"""
        
        if not date:
            date = datetime.now().date()
        
        logger.info(f"Running standup for team {team_id} on {date}")
        
        try:
            # Step 1: Gather data from various sources
            standup_data = await self._gather_standup_data(team_id, sprint_id, date)
            
            # Step 2: Generate AI summary
            summary = await self._generate_standup_summary(standup_data)
            
            # Step 3: Identify action items
            action_items = await self._identify_action_items(standup_data, summary)
            
            # Step 4: Format final output
            result = {
                "date": date.isoformat(),
                "team_id": team_id,
                "sprint_id": sprint_id,
                "summary": summary,
                "action_items": action_items,
                "raw_data": standup_data,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Standup execution error: {str(e)}")
            raise
    
    async def _gather_standup_data(self, team_id: int, sprint_id: Optional[int], date: date) -> Dict[str, Any]:
        """Gather all relevant standup data"""
        
        data = {
            "jira_updates": [],
            "slack_messages": [],
            "team_members": [],
            "sprint_progress": {}
        }
        
        try:
            # Get Jira updates from yesterday
            if self.jira_client:
                yesterday = date.replace(day=date.day - 1)
                data["jira_updates"] = await self.jira_client.get_daily_updates(
                    team_id=team_id,
                    date=yesterday
                )
                
                if sprint_id:
                    data["sprint_progress"] = await self.jira_client.get_sprint_progress(sprint_id)
            
            # Get Slack standup messages
            if self.slack_client:
                data["slack_messages"] = await self.slack_client.get_standup_messages(
                    team_id=team_id,
                    date=date
                )
            
            # Get team member list
            # This would come from your database
            data["team_members"] = await self._get_team_members(team_id)
            
        except Exception as e:
            logger.warning(f"Error gathering standup data: {str(e)}")
        
        return data
    
    async def _generate_standup_summary(self, standup_data: Dict[str, Any]) -> str:
        """Generate AI-powered standup summary"""
        
        prompt = f"""
        Generate a standup summary based on the following data:
        
        Jira Updates: {json.dumps(standup_data.get('jira_updates', []), indent=2)}
        Slack Messages: {json.dumps(standup_data.get('slack_messages', []), indent=2)}
        Sprint Progress: {json.dumps(standup_data.get('sprint_progress', {}), indent=2)}
        Team Members: {standup_data.get('team_members', [])}
        
        Please create a structured standup summary following this format:
        
        ## COMPLETED YESTERDAY
        - [List accomplishments]
        
        ## PLANNED TODAY  
        - [List planned work]
        
        ## BLOCKERS
        - [List any blockers or impediments]
        
        ## NOTES
        - [Additional observations, risks, or suggestions]
        """
        
        response = await self.ai_engine.generate_response(
            prompt=prompt,
            operation_type="standup_summary",
            team_id=standup_data.get("team_id")
        )
        
        return response["response"]
    
    async def _identify_action_items(self, standup_data: Dict[str, Any], summary: str) -> List[Dict[str, Any]]:
        """Identify and structure action items from standup"""
        
        prompt = f"""
        Based on this standup summary and data, identify specific action items:
        
        Summary: {summary}
        
        Return a JSON array of action items with this structure:
        [
            {{
                "description": "Clear description of action needed",
                "assignee": "person responsible (if identifiable)",
                "priority": "high|medium|low",
                "type": "blocker_resolution|follow_up|process_improvement",
                "due_date": "estimated completion date if applicable"
            }}
        ]
        
        Focus on actionable items that can help the team progress.
        """
        
        response = await self.ai_engine.generate_response(
            prompt=prompt,
            operation_type="standup_summary"
        )
        
        try:
            return json.loads(response["response"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse action items JSON")
            return []
    
    async def _get_team_members(self, team_id: int) -> List[str]:
        """Get team member list from database"""
        # This would integrate with your database
        # For now, return placeholder
        return ["Team Member 1", "Team Member 2", "Team Member 3"]
