from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from ..models.backlog import BacklogItem
from ..models.user import Team, TeamMembership
from ..agents.backlog_agent import BacklogAgent
from ..integrations.jira_client import JiraClient
from ..services.ai_engine import AIEngine
from ..utils.logging import get_logger

logger = get_logger(__name__)


class BacklogService:
    """Service for managing backlog operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_engine = AIEngine()
    
    async def analyze_backlog(
        self,
        team_id: int,
        item_ids: Optional[List[int]] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run AI analysis on backlog items"""
        
        logger.info(f"Analyzing backlog for team {team_id}")
        
        try:
            # Get team and integration settings
            team = await self._get_team_with_integrations(team_id)
            if not team:
                raise ValueError("Team not found")
            
            # Initialize integrations
            jira_client = JiraClient(team=team) if team.jira_project_key else None
            
            # Initialize backlog agent
            backlog_agent = BacklogAgent(
                ai_engine=self.ai_engine,
                jira_client=jira_client
            )
            
            # Run analysis
            analysis_result = await backlog_agent.execute(
                team_id=team_id,
                backlog_item_ids=item_ids
            )
            
            # Update database with analysis results
            await self._store_analysis_results(analysis_result, user_id)
            
            logger.info(f"Backlog analysis completed for team {team_id}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Backlog analysis failed: {str(e)}")
            raise
    
    async def get_team_backlog(
        self,
        team_id: int,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[BacklogItem]:
        """Get backlog items for a team"""
        
        stmt = select(BacklogItem).where(BacklogItem.team_id == team_id)
        
        if status:
            stmt = stmt.where(BacklogItem.status == status)
        
        if priority:
            stmt = stmt.where(BacklogItem.priority == priority)
        
        stmt = stmt.order_by(BacklogItem.priority.desc(), BacklogItem.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_backlog_item(self, item_id: int) -> Optional[BacklogItem]:
        """Get backlog item by ID"""
        
        stmt = select(BacklogItem).where(BacklogItem.id == item_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def apply_ai_suggestions(
        self,
        item_id: int,
        suggestions_to_apply: List[str],
        user_id: int
    ) -> BacklogItem:
        """Apply AI suggestions to a backlog item"""
        
        item = await self.get_backlog_item(item_id)
        if not item:
            raise ValueError("Backlog item not found")
        
        ai_suggestions = item.ai_suggestions or {}
        
        try:
            for suggestion_type in suggestions_to_apply:
                if suggestion_type in ai_suggestions:
                    suggestion = ai_suggestions[suggestion_type]
                    
                    if suggestion_type == "description":
                        item.description = suggestion.get("improved_text", item.description)
                    
                    elif suggestion_type == "acceptance_criteria":
                        # Store in description or separate field
                        criteria = suggestion.get("criteria", [])
                        if criteria:
                            item.description += f"\n\nAcceptance Criteria:\n" + "\n".join(f"- {c}" for c in criteria)
                    
                    elif suggestion_type == "story_points":
                        item.story_points = suggestion.get("estimated_points")
                    
                    elif suggestion_type == "priority":
                        item.priority = suggestion.get("suggested_priority", item.priority)
            
            # Mark suggestions as applied
            applied_suggestions = item.ai_suggestions.get("applied", [])
            applied_suggestions.extend(suggestions_to_apply)
            item.ai_suggestions["applied"] = list(set(applied_suggestions))
            item.ai_suggestions["applied_by"] = user_id
            item.ai_suggestions["applied_at"] = datetime.utcnow().isoformat()
            
            await self.db.commit()
            await self.db.refresh(item)
            
            logger.info(f"Applied AI suggestions to item {item_id}: {suggestions_to_apply}")
            return item
            
        except Exception as e:
            logger.error(f"Failed to apply suggestions: {str(e)}")
            await self.db