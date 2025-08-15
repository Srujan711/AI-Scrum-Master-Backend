from typing import List, Optional, Dict, Any
from datetime import date, datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ..models.standup import StandupSummary
from ..models.user import Team, TeamMembership
from ..models.user import User
from ..models.sprint import Sprint
from ..agents.standup_agent import StandupAgent
from ..integrations.jira_client import JiraClient
from ..integrations.slack_client import SlackClient
from ..services.ai_engine import AIEngine
from ..utils.logging import get_logger

logger = get_logger(__name__)


class StandupService:
    """Service for managing standup operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_engine = AIEngine()
    
    async def generate_standup_summary(
        self,
        team_id: int,
        sprint_id: Optional[int] = None,
        date: date = None,
        creator_id: int = None,
        manual_input: Optional[Dict[str, Any]] = None
    ) -> StandupSummary:
        """Generate AI-powered standup summary"""
        
        if not date:
            date = datetime.now().date()
        
        logger.info(f"Generating standup summary for team {team_id} on {date}")
        
        try:
            # Get team and integration tokens
            team = await self._get_team_with_integrations(team_id)
            if not team:
                raise ValueError("Team not found")
            
            # Initialize integrations
            jira_client = JiraClient(team=team) if team.jira_project_key else None
            slack_client = SlackClient(team=team) if team.slack_channel_id else None
            
            # Initialize standup agent
            standup_agent = StandupAgent(
                ai_engine=self.ai_engine,
                jira_client=jira_client,
                slack_client=slack_client
            )
            
            # Generate standup summary
            agent_result = await standup_agent.execute(
                team_id=team_id,
                sprint_id=sprint_id,
                date=date
            )
            
            # Create database record
            standup_summary = StandupSummary(
                date=date,
                summary_text=agent_result["summary"],
                completed_yesterday=agent_result.get("completed_yesterday", []),
                planned_today=agent_result.get("planned_today", []),
                blockers=agent_result.get("blockers", []),
                action_items=agent_result.get("action_items", []),
                ai_generated=True,
                human_approved=False,
                team_id=team_id,
                sprint_id=sprint_id,
                creator_id=creator_id,
                ai_insights=agent_result.get("ai_insights", {}),
                risk_indicators=agent_result.get("risk_indicators", [])
            )
            
            self.db.add(standup_summary)
            await self.db.commit()
            await self.db.refresh(standup_summary)
            
            logger.info(f"Generated standup summary {standup_summary.id}")
            return standup_summary
            
        except Exception as e:
            logger.error(f"Failed to generate standup summary: {str(e)}")
            await self.db.rollback()
            raise
    
    async def get_standup(self, standup_id: int) -> Optional[StandupSummary]:
        """Get standup summary by ID"""
        
        stmt = select(StandupSummary).where(StandupSummary.id == standup_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_standup(self, standup_id: int, **updates) -> StandupSummary:
        """Update standup summary"""
        
        standup = await self.get_standup(standup_id)
        if not standup:
            raise ValueError("Standup not found")
        
        for key, value in updates.items():
            if hasattr(standup, key):
                setattr(standup, key, value)
        
        standup.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(standup)
        
        return standup
    
    async def approve_standup(self, standup_id: int, approver_id: int) -> StandupSummary:
        """Approve standup summary"""
        
        return await self.update_standup(
            standup_id=standup_id,
            human_approved=True,
            approver_id=approver_id
        )
    
    async def get_team_standups(
        self,
        team_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[StandupSummary]:
        """Get standup summaries for a team"""
        
        stmt = (
            select(StandupSummary)
            .where(StandupSummary.team_id == team_id)
            .order_by(StandupSummary.date.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def post_to_slack(self, standup_id: int):
        """Post standup summary to Slack"""
        
        standup = await self.get_standup(standup_id)
        if not standup:
            raise ValueError("Standup not found")
        
        team = await self._get_team_with_integrations(standup.team_id)
        if not team or not team.slack_channel_id:
            logger.warning(f"No Slack integration for team {standup.team_id}")
            return
        
        try:
            slack_client = SlackClient(team=team)
            await slack_client.post_standup_summary(standup)
            
            # Update posted status
            await self.update_standup(standup_id, posted_to_slack=True)
            
        except Exception as e:
            logger.error(f"Failed to post standup to Slack: {str(e)}")
            raise
    
    async def user_has_access(self, user_id: int, team_id: int) -> bool:
        """Check if user has access to team"""
        
        stmt = select(TeamMembership).where(
            and_(
                TeamMembership.user_id == user_id,
                TeamMembership.team_id == team_id,
                TeamMembership.is_active == True
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
    
    async def _get_team_with_integrations(self, team_id: int) -> Optional[Team]:
        """Get team with integration settings"""
        
        stmt = select(Team).where(Team.id == team_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
