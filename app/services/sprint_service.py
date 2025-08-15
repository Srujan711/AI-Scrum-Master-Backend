from __future__ import annotations

from typing import (
    Any, 
    Dict, 
    List, 
    Optional, 
    Tuple, 
    Union,
    TYPE_CHECKING
)
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass
from enum import Enum
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, desc
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field, validator

if TYPE_CHECKING:
    from ..models.sprint import Sprint
    from ..models.backlog import BacklogItem
    from ..models.user import Team
    from ..models.user import User
    from ..services.ai_engine import AIEngine

# Type aliases
TeamId = int
SprintId = int
UserId = int
BacklogItemId = int
StoryPoints = int

# Enums
class SprintStatus(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class VelocityTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"

class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# Pydantic models
class BacklogItemSummary(BaseModel):
    id: BacklogItemId
    title: str
    description: str = ""
    story_points: StoryPoints = 0
    priority: str
    status: str
    clarity_score: float = 0.5
    jira_key: Optional[str] = None

class VelocityMetrics(BaseModel):
    average_velocity: float
    velocity_trend: VelocityTrend
    sprints_analyzed: int
    confidence: ConfidenceLevel

class RiskFactor(BaseModel):
    type: str
    severity: RiskSeverity
    description: str
    affected_items: List[BacklogItemId] = Field(default_factory=list)
    mitigation: str

class RecommendedItem(BaseModel):
    item_id: BacklogItemId
    title: str
    story_points: StoryPoints
    priority: str
    selection_reason: str

class SprintPlanningResult(BaseModel):
    team_id: TeamId
    recommended_items: List[RecommendedItem]
    total_capacity: StoryPoints
    recommended_points: StoryPoints
    utilization_percentage: float
    risk_assessment: List[RiskFactor]
    suggested_goal: str
    velocity_forecast: VelocityMetrics
    confidence_score: float
    generated_at: datetime

class CurrentSprintMetrics(BaseModel):
    total_items: int
    completed_items: int
    in_progress_items: int
    blocked_items: int
    total_points: StoryPoints
    completed_points: StoryPoints
    remaining_points: StoryPoints
    completion_rate: float
    current_velocity: float
    days_elapsed: int
    days_remaining: int

class CompletionForecast(BaseModel):
    completion_probability: str
    projected_completion_date: Optional[date]
    days_needed: Optional[int]
    likelihood: str
    recommendations: List[str] = Field(default_factory=list)

class DailyBurndownPoint(BaseModel):
    date: date
    remaining_points: StoryPoints
    ideal_remaining: float
    is_weekend: bool = False

class BurndownAnalysis(BaseModel):
    sprint_id: SprintId
    sprint_name: str
    daily_data: List[DailyBurndownPoint]
    current_metrics: CurrentSprintMetrics
    completion_forecast: CompletionForecast
    generated_at: datetime

# Custom exceptions
class SprintServiceError(Exception):
    def __init__(self, message: str, sprint_id: Optional[SprintId] = None) -> None:
        super().__init__(message)
        self.sprint_id = sprint_id

class SprintValidationError(SprintServiceError):
    pass

class SprintNotFoundError(SprintServiceError):
    def __init__(self, sprint_id: SprintId) -> None:
        super().__init__(f"Sprint {sprint_id} not found", sprint_id)

class InvalidStatusTransitionError(SprintServiceError):
    def __init__(self, current: str, new: str) -> None:
        super().__init__(f"Invalid transition from {current} to {new}")

# Main service class
class SprintService:
    """
    Production-quality sprint service with proper typing.
    
    Handles sprint planning, progress tracking, and analytics.
    """
    
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._logger = logging.getLogger(__name__)
    
    async def generate_sprint_plan(
        self,
        team_id: TeamId,
        capacity_points: Optional[StoryPoints] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        user_id: Optional[UserId] = None
    ) -> SprintPlanningResult:
        """Generate AI-powered sprint planning recommendations."""
        
        self._logger.info("Generating sprint plan for team %d", team_id)
        
        try:
            # Validate team exists
            await self._validate_team_exists(team_id)
            
            # Calculate capacity if not provided
            if capacity_points is None:
                capacity_points = await self._calculate_team_capacity(team_id)
            
            # Get velocity metrics
            velocity_metrics = await self._get_velocity_metrics(team_id)
            
            # Get backlog items
            backlog_items = await self._get_planning_backlog(team_id)
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(
                team_id, capacity_points, backlog_items, velocity_metrics
            )
            
            # Build result
            result = SprintPlanningResult(
                team_id=team_id,
                recommended_items=recommendations["items"],
                total_capacity=capacity_points,
                recommended_points=recommendations["total_points"],
                utilization_percentage=self._calculate_utilization(
                    recommendations["total_points"], capacity_points
                ),
                risk_assessment=recommendations["risks"],
                suggested_goal=recommendations["goal"],
                velocity_forecast=velocity_metrics,
                confidence_score=recommendations["confidence"],
                generated_at=datetime.now(timezone.utc)
            )
            
            self._logger.info("Sprint planning completed for team %d", team_id)
            return result
            
        except Exception as e:
            self._logger.error("Sprint planning failed for team %d: %s", team_id, str(e))
            if isinstance(e, SprintServiceError):
                raise
            raise SprintServiceError(f"Sprint planning failed: {str(e)}")
    
    async def create_sprint(
        self,
        team_id: TeamId,
        name: str,
        start_date: date,
        end_date: date,
        capacity_points: Optional[StoryPoints] = None,
        suggested_items: Optional[List[BacklogItemId]] = None,
        goal: Optional[str] = None,
        creator_id: Optional[UserId] = None
    ) -> Sprint:
        """Create a new sprint with validation."""
        
        from ..models.sprint import Sprint
        
        self._logger.info("Creating sprint '%s' for team %d", name, team_id)
        
        try:
            # Validate inputs
            self._validate_sprint_dates(start_date, end_date)
            await self._validate_team_exists(team_id)
            await self._validate_no_overlapping_sprints(team_id, start_date, end_date)
            
            # Generate AI insights
            ai_insights: Dict[str, Any] = {}
            risk_factors: List[str] = []
            
            if suggested_items:
                risks = await self._analyze_item_risks(suggested_items)
                ai_insights["risks"] = [risk.model_dump() for risk in risks]
                risk_factors = [risk.description for risk in risks]
                
                if not goal:
                    goal = await self._generate_sprint_goal(suggested_items)
            
            # Calculate capacity
            if capacity_points is None and suggested_items:
                capacity_points = await self._calculate_items_total_points(suggested_items)
            
            # Create sprint
            sprint = Sprint(
                name=name,
                goal=goal,
                start_date=start_date,
                end_date=end_date,
                status=SprintStatus.PLANNING.value,
                planned_capacity=capacity_points,
                completed_points=0,
                team_id=team_id,
                ai_insights=ai_insights,
                risk_factors=risk_factors
            )
            
            self.db.add(sprint)
            await self.db.flush()
            
            # Assign items
            if suggested_items:
                await self._assign_items_to_sprint(suggested_items, sprint.id)
            
            await self.db.commit()
            await self.db.refresh(sprint)
            
            self._logger.info("Created sprint %d", sprint.id)
            return sprint
            
        except Exception as e:
            await self.db.rollback()
            self._logger.error("Failed to create sprint: %s", str(e))
            if isinstance(e, SprintServiceError):
                raise
            raise SprintServiceError(f"Sprint creation failed: {str(e)}")
    
    async def get_sprint(self, sprint_id: SprintId) -> Sprint:
        """Get sprint by ID."""
        
        from ..models.sprint import Sprint
        
        stmt = (
            select(Sprint)
            .options(selectinload(Sprint.backlog_items))
            .where(Sprint.id == sprint_id)
        )
        
        result = await self.db.execute(stmt)
        sprint = result.scalar_one_or_none()
        
        if sprint is None:
            raise SprintNotFoundError(sprint_id)
        
        return sprint
    
    async def update_sprint_status(
        self,
        sprint_id: SprintId,
        status: SprintStatus,
        user_id: Optional[UserId] = None
    ) -> Sprint:
        """Update sprint status with validation."""
        
        sprint = await self.get_sprint(sprint_id)
        current_status = SprintStatus(sprint.status)
        
        if not self._is_valid_status_transition(current_status, status):
            raise InvalidStatusTransitionError(current_status.value, status.value)
        
        if status == SprintStatus.COMPLETED:
            await self._calculate_completion_metrics(sprint)
        
        sprint.status = status.value
        sprint.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(sprint)
        
        self._logger.info("Updated sprint %d status to %s", sprint_id, status.value)
        return sprint
    
    async def generate_burndown_analysis(self, sprint_id: SprintId) -> BurndownAnalysis:
        """Generate burndown analysis."""
        
        sprint = await self.get_sprint(sprint_id)
        
        try:
            daily_data = await self._calculate_daily_burndown(sprint)
            current_metrics = await self._calculate_current_metrics(sprint)
            completion_forecast = self._generate_completion_forecast(current_metrics)
            
            return BurndownAnalysis(
                sprint_id=sprint_id,
                sprint_name=sprint.name,
                daily_data=daily_data,
                current_metrics=current_metrics,
                completion_forecast=completion_forecast,
                generated_at=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            self._logger.error("Burndown analysis failed: %s", str(e))
            raise SprintServiceError(f"Burndown analysis failed: {str(e)}")
    
    async def get_team_sprints(
        self,
        team_id: TeamId,
        status: Optional[SprintStatus] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Sprint]:
        """Get sprints for a team."""
        
        from ..models.sprint import Sprint
        
        stmt = select(Sprint).where(Sprint.team_id == team_id)
        
        if status is not None:
            stmt = stmt.where(Sprint.status == status.value)
        
        stmt = stmt.order_by(desc(Sprint.start_date)).limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def user_has_access(self, user_id: UserId, team_id: TeamId) -> bool:
        """Check if user has access to team."""
        
        from ..models.user import TeamMembership
        
        stmt = select(TeamMembership).where(
            and_(
                TeamMembership.user_id == user_id,
                TeamMembership.team_id == team_id,
                TeamMembership.is_active == True
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
    
    # Private methods
    
    async def _validate_team_exists(self, team_id: TeamId) -> None:
        """Validate team exists."""
        
        from ..models.user import Team
        
        stmt = select(Team).where(Team.id == team_id)
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()
        
        if team is None:
            raise SprintValidationError(f"Team {team_id} not found")
    
    def _validate_sprint_dates(self, start_date: date, end_date: date) -> None:
        """Validate sprint dates."""
        
        if start_date >= end_date:
            raise SprintValidationError("Start date must be before end date")
        
        if start_date < date.today():
            raise SprintValidationError("Start date cannot be in the past")
        
        duration = (end_date - start_date).days
        if duration > 30:
            raise SprintValidationError("Sprint duration cannot exceed 30 days")
    
    async def _validate_no_overlapping_sprints(
        self,
        team_id: TeamId,
        start_date: date,
        end_date: date
    ) -> None:
        """Validate no overlapping sprints."""
        
        from ..models.sprint import Sprint
        
        stmt = select(Sprint).where(
            and_(
                Sprint.team_id == team_id,
                Sprint.status.in_([SprintStatus.PLANNING.value, SprintStatus.ACTIVE.value]),
                or_(
                    and_(Sprint.start_date <= start_date, Sprint.end_date > start_date),
                    and_(Sprint.start_date < end_date, Sprint.end_date >= end_date)
                )
            )
        )
        
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing is not None:
            raise SprintValidationError(f"Overlapping sprint exists: {existing.name}")
    
    def _is_valid_status_transition(self, current: SprintStatus, new: SprintStatus) -> bool:
        """Check valid status transitions."""
        
        valid_transitions: Dict[SprintStatus, List[SprintStatus]] = {
            SprintStatus.PLANNING: [SprintStatus.ACTIVE, SprintStatus.CANCELLED],
            SprintStatus.ACTIVE: [SprintStatus.COMPLETED, SprintStatus.CANCELLED],
            SprintStatus.COMPLETED: [],
            SprintStatus.CANCELLED: [SprintStatus.PLANNING]
        }
        
        return new in valid_transitions.get(current, [])
    
    async def _calculate_team_capacity(self, team_id: TeamId) -> StoryPoints:
        """Calculate team capacity."""
        
        from ..models.user import TeamMembership
        
        stmt = select(func.count(TeamMembership.id)).where(
            and_(
                TeamMembership.team_id == team_id,
                TeamMembership.is_active == True
            )
        )
        
        result = await self.db.execute(stmt)
        member_count = result.scalar() or 0
        
        # Simple calculation: 8 points per member for 2-week sprint
        return max(member_count * 8, 1)
    
    async def _get_velocity_metrics(self, team_id: TeamId) -> VelocityMetrics:
        """Get team velocity metrics."""
        
        from ..models.sprint import Sprint
        
        stmt = (
            select(Sprint)
            .where(
                and_(
                    Sprint.team_id == team_id,
                    Sprint.status == SprintStatus.COMPLETED.value,
                    Sprint.velocity.isnot(None)
                )
            )
            .order_by(desc(Sprint.end_date))
            .limit(5)
        )
        
        result = await self.db.execute(stmt)
        sprints = list(result.scalars().all())
        
        if not sprints:
            return VelocityMetrics(
                average_velocity=0.0,
                velocity_trend=VelocityTrend.INSUFFICIENT_DATA,
                sprints_analyzed=0,
                confidence=ConfidenceLevel.LOW
            )
        
        velocities = [float(sprint.velocity) for sprint in sprints if sprint.velocity]
        
        if not velocities:
            return VelocityMetrics(
                average_velocity=0.0,
                velocity_trend=VelocityTrend.INSUFFICIENT_DATA,
                sprints_analyzed=len(sprints),
                confidence=ConfidenceLevel.LOW
            )
        
        avg_velocity = sum(velocities) / len(velocities)
        trend = self._analyze_velocity_trend(velocities)
        confidence = self._calculate_confidence(velocities)
        
        return VelocityMetrics(
            average_velocity=round(avg_velocity, 2),
            velocity_trend=trend,
            sprints_analyzed=len(sprints),
            confidence=confidence
        )
    
    def _analyze_velocity_trend(self, velocities: List[float]) -> VelocityTrend:
        """Analyze velocity trend."""
        
        if len(velocities) < 3:
            return VelocityTrend.INSUFFICIENT_DATA
        
        mid = len(velocities) // 2
        recent_avg = sum(velocities[:mid]) / mid
        older_avg = sum(velocities[mid:]) / (len(velocities) - mid)
        
        if recent_avg > older_avg * 1.15:
            return VelocityTrend.IMPROVING
        elif recent_avg < older_avg * 0.85:
            return VelocityTrend.DECLINING
        else:
            return VelocityTrend.STABLE
    
    def _calculate_confidence(self, velocities: List[float]) -> ConfidenceLevel:
        """Calculate confidence level."""
        
        if len(velocities) < 3:
            return ConfidenceLevel.LOW
        
        avg = sum(velocities) / len(velocities)
        if avg == 0:
            return ConfidenceLevel.LOW
        
        # Calculate coefficient of variation
        variance = sum((v - avg) ** 2 for v in velocities) / len(velocities)
        std_dev = variance ** 0.5
        cv = std_dev / avg
        
        if len(velocities) >= 5 and cv < 0.2:
            return ConfidenceLevel.HIGH
        elif len(velocities) >= 3 and cv < 0.3:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    async def _get_planning_backlog(self, team_id: TeamId) -> List[BacklogItemSummary]:
        """Get backlog items for planning."""
        
        from ..models.backlog import BacklogItem
        
        stmt = (
            select(BacklogItem)
            .where(
                and_(
                    BacklogItem.team_id == team_id,
                    BacklogItem.sprint_id.is_(None),
                    BacklogItem.status == "to_do"
                )
            )
            .order_by(BacklogItem.priority.desc())
            .limit(50)
        )
        
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        return [
            BacklogItemSummary(
                id=item.id,
                title=item.title,
                description=item.description or "",
                story_points=item.story_points or 0,
                priority=item.priority,
                status=item.status,
                clarity_score=item.clarity_score or 0.5,
                jira_key=item.jira_key
            )
            for item in items
        ]
    
    async def _generate_recommendations(
        self,
        team_id: TeamId,
        capacity: StoryPoints,
        backlog: List[BacklogItemSummary],
        velocity: VelocityMetrics
    ) -> Dict[str, Any]:
        """Generate sprint recommendations."""
        
        # Simple rule-based selection for now
        # In production, this would use AI
        
        selected_items: List[RecommendedItem] = []
        total_points = 0
        
        # Sort by priority and clarity
        priority_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        sorted_items = sorted(
            backlog,
            key=lambda x: (
                priority_weights.get(x.priority, 1),
                x.clarity_score,
                -x.story_points
            ),
            reverse=True
        )
        
        for item in sorted_items:
            if item.story_points == 0:
                continue
            
            if total_points + item.story_points <= capacity:
                selected_items.append(
                    RecommendedItem(
                        item_id=item.id,
                        title=item.title,
                        story_points=item.story_points,
                        priority=item.priority,
                        selection_reason="High priority, fits capacity"
                    )
                )
                total_points += item.story_points
            
            if total_points >= capacity * 0.9:
                break
        
        return {
            "items": selected_items,
            "total_points": total_points,
            "goal": f"Complete {len(selected_items)} high-priority items",
            "risks": [],
            "confidence": 0.8
        }
    
    def _calculate_utilization(self, planned: StoryPoints, capacity: StoryPoints) -> float:
        """Calculate capacity utilization percentage."""
        
        if capacity == 0:
            return 0.0
        
        return round((planned / capacity) * 100, 1)
    
    async def _analyze_item_risks(self, item_ids: List[BacklogItemId]) -> List[RiskFactor]:
        """Analyze risks for items."""
        
        from ..models.backlog import BacklogItem
        
        stmt = select(BacklogItem).where(BacklogItem.id.in_(item_ids))
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        risks: List[RiskFactor] = []
        
        # Check for large items
        large_items = [item for item in items if (item.story_points or 0) > 8]
        if large_items:
            risks.append(
                RiskFactor(
                    type="large_stories",
                    severity=RiskSeverity.HIGH,
                    description=f"{len(large_items)} items larger than 8 points",
                    affected_items=[item.id for item in large_items],
                    mitigation="Break down large stories"
                )
            )
        
        # Check for unclear items
        unclear_items = [item for item in items if (item.clarity_score or 0) < 0.7]
        if unclear_items:
            risks.append(
                RiskFactor(
                    type="unclear_requirements",
                    severity=RiskSeverity.MEDIUM,
                    description=f"{len(unclear_items)} items have unclear requirements",
                    affected_items=[item.id for item in unclear_items],
                    mitigation="Clarify requirements before sprint start"
                )
            )
        
        return risks
    
    async def _generate_sprint_goal(self, item_ids: List[BacklogItemId]) -> str:
        """Generate sprint goal."""
        
        # Simple implementation - in production would use AI
        return f"Complete {len(item_ids)} high-priority backlog items"
    
    async def _calculate_items_total_points(self, item_ids: List[BacklogItemId]) -> StoryPoints:
        """Calculate total points for items."""
        
        from ..models.backlog import BacklogItem
        
        stmt = select(func.sum(BacklogItem.story_points)).where(
            BacklogItem.id.in_(item_ids)
        )
        
        result = await self.db.execute(stmt)
        total = result.scalar() or 0
        return int(total)
    
    async def _assign_items_to_sprint(
        self,
        item_ids: List[BacklogItemId],
        sprint_id: SprintId
    ) -> None:
        """Assign items to sprint."""
        
        from ..models.backlog import BacklogItem
        
        stmt = select(BacklogItem).where(BacklogItem.id.in_(item_ids))
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        for item in items:
            item.sprint_id = sprint_id
            item.status = "to_do"
    
    async def _calculate_completion_metrics(self, sprint: Sprint) -> None:
        """Calculate completion metrics."""
        
        from ..models.backlog import BacklogItem
        
        stmt = select(BacklogItem).where(BacklogItem.sprint_id == sprint.id)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        if not items:
            return
        
        completed_points = sum(
            item.story_points or 0
            for item in items
            if item.status == "done"
        )
        
        sprint_days = (sprint.end_date - sprint.start_date).days
        velocity = completed_points / sprint_days if sprint_days > 0 else 0
        
        sprint.completed_points = completed_points
        sprint.velocity = velocity
    
    async def _calculate_daily_burndown(self, sprint: Sprint) -> List[DailyBurndownPoint]:
        """Calculate daily burndown data."""
        
        daily_data: List[DailyBurndownPoint] = []
        current_date = sprint.start_date
        
        while current_date <= min(sprint.end_date, date.today()):
            remaining = await self._get_remaining_work(sprint.id, current_date)
            ideal = self._calculate_ideal_remaining(sprint, current_date)
            
            daily_data.append(
                DailyBurndownPoint(
                    date=current_date,
                    remaining_points=remaining,
                    ideal_remaining=ideal,
                    is_weekend=current_date.weekday() >= 5
                )
            )
            
            current_date += timedelta(days=1)
        
        return daily_data
    
    async def _get_remaining_work(self, sprint_id: SprintId, target_date: date) -> StoryPoints:
        """Get remaining work on date."""
        
        from ..models.backlog import BacklogItem
        
        # Simple implementation - would use status history in production
        stmt = select(func.sum(BacklogItem.story_points)).where(
            and_(
                BacklogItem.sprint_id == sprint_id,
                BacklogItem.status != "done"
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    def _calculate_ideal_remaining(self, sprint: Sprint, target_date: date) -> float:
        """Calculate ideal remaining work."""
        
        total_days = (sprint.end_date - sprint.start_date).days
        days_passed = (target_date - sprint.start_date).days
        
        if total_days <= 0:
            return 0.0
        
        capacity = float(sprint.planned_capacity or 0)
        progress = days_passed / total_days
        
        return max(0.0, capacity * (1.0 - progress))
    
    async def _calculate_current_metrics(self, sprint: Sprint) -> CurrentSprintMetrics:
        """Calculate current sprint metrics."""
        
        from ..models.backlog import BacklogItem
        
        stmt = select(BacklogItem).where(BacklogItem.sprint_id == sprint.id)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        
        if not items:
            return CurrentSprintMetrics(
                total_items=0,
                completed_items=0,
                in_progress_items=0,
                blocked_items=0,
                total_points=0,
                completed_points=0,
                remaining_points=0,
                completion_rate=0.0,
                current_velocity=0.0,
                days_elapsed=0,
                days_remaining=0
            )
        
        total_items = len(items)
        completed_items = len([item for item in items if item.status == "done"])
        in_progress_items = len([item for item in items if item.status == "in_progress"])
        blocked_items = len([item for item in items if item.status == "blocked"])
        
        total_points = sum(item.story_points or 0 for item in items)
        completed_points = sum(
            item.story_points or 0 for item in items if item.status == "done"
        )
        
        days_elapsed = max((date.today() - sprint.start_date).days, 0)
        days_remaining = max((sprint.end_date - date.today()).days, 0)
        
        completion_rate = (completed_points / total_points * 100) if total_points > 0 else 0.0
        current_velocity = completed_points / max(days_elapsed, 1)
        
        return CurrentSprintMetrics(
            total_items=total_items,
            completed_items=completed_items,
            in_progress_items=in_progress_items,
            blocked_items=blocked_items,
            total_points=total_points,
            completed_points=completed_points,
            remaining_points=total_points - completed_points,
            completion_rate=round(completion_rate, 1),
            current_velocity=round(current_velocity, 2),
            days_elapsed=days_elapsed,
            days_remaining=days_remaining
        )
    
    def _generate_completion_forecast(self, metrics: CurrentSprintMetrics) -> CompletionForecast:
        """Generate completion forecast."""
        
        if metrics.current_velocity <= 0:
            return CompletionForecast(
                completion_probability="unknown",
                projected_completion_date=None,
                days_needed=None,
                likelihood="Cannot determine without velocity data",
                recommendations=["Track progress and update estimates"]
            )
        
        days_needed = int(metrics.remaining_points / metrics.current_velocity)
        projected_date = date.today() + timedelta(days=days_needed)
        
        # Determine probability
        if days_needed <= metrics.days_remaining * 0.8:
            probability = "high"
            likelihood = "Very likely to complete on time"
        elif days_needed <= metrics.days_remaining:
            probability = "medium"
            likelihood = "Likely to complete on time"
        elif days_needed <= metrics.days_remaining * 1.2:
            probability = "low"
            likelihood = "May require scope adjustment"
        else:
            probability = "very_low"
            likelihood = "Unlikely without significant changes"
        
        # Generate recommendations
        recommendations = self._get_forecast_recommendations(probability)
        
        return CompletionForecast(
            completion_probability=probability,
            projected_completion_date=projected_date,
            days_needed=days_needed,
            likelihood=likelihood,
            recommendations=recommendations
        )
    
    def _get_forecast_recommendations(self, probability: str) -> List[str]:
        """Get recommendations based on completion probability."""
        
        if probability == "very_low":
            return [
                "Consider reducing sprint scope immediately",
                "Identify and remove blocked items",
                "Focus on highest priority items only"
            ]
        elif probability == "low":
            return [
                "Review scope and consider removing lower priority items",
                "Address any blockers quickly",
                "Increase team focus on sprint goal"
            ]
        elif probability == "medium":
            return [
                "Monitor progress closely",
                "Be prepared to adjust scope if needed",
                "Ensure team is focused on commitments"
            ]
        else:  # high
            return [
                "Current pace is good",
                "Consider adding stretch goals if appropriate",
                "Maintain current momentum"
            ]


# Usage example with proper typing
async def example_usage() -> None:
    """Example of how to use the SprintService with proper typing."""
    
    # This would be injected in real application
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # Mock db session for example
    db: AsyncSession = None  # type: ignore
    
    # Initialize service
    service = SprintService(db)
    
    try:
        # Generate sprint plan
        plan: SprintPlanningResult = await service.generate_sprint_plan(
            team_id=1,
            capacity_points=25,
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=15)
        )
        
        print(f"Plan generated: {plan.recommended_items}")
        print(f"Utilization: {plan.utilization_percentage}%")
        
        # Create sprint
        sprint: Sprint = await service.create_sprint(
            team_id=1,
            name="Sprint 24",
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=15),
            suggested_items=[item.item_id for item in plan.recommended_items]
        )
        
        print(f"Sprint created: {sprint.name}")
        
        # Update status
        updated_sprint: Sprint = await service.update_sprint_status(
            sprint_id=sprint.id,
            status=SprintStatus.ACTIVE
        )
        
        print(f"Sprint status: {updated_sprint.status}")
        
        # Get burndown analysis
        burndown: BurndownAnalysis = await service.generate_burndown_analysis(
            sprint_id=sprint.id
        )
        
        print(f"Burndown generated for: {burndown.sprint_name}")
        print(f"Completion forecast: {burndown.completion_forecast.completion_probability}")
        
        # Get team sprints
        team_sprints: List[Sprint] = await service.get_team_sprints(
            team_id=1,
            status=SprintStatus.ACTIVE,
            limit=5
        )
        
        print(f"Active sprints: {len(team_sprints)}")
        
        # Check access
        has_access: bool = await service.user_has_access(
            user_id=123,
            team_id=1
        )
        
        print(f"User has access: {has_access}")
        
    except SprintNotFoundError as e:
        print(f"Sprint not found: {e.sprint_id}")
    except SprintValidationError as e:
        print(f"Validation error: {e}")
    except InvalidStatusTransitionError as e:
        print(f"Invalid transition: {e}")
    except SprintServiceError as e:
        print(f"Service error: {e}")


# Type-safe factory function
def create_sprint_service(db: AsyncSession) -> SprintService:
    """Create a properly typed SprintService instance."""
    return SprintService(db)


# Type guards for runtime validation
def is_valid_sprint_status(status: str) -> bool:
    """Type guard to check if string is valid SprintStatus."""
    try:
        SprintStatus(status)
        return True
    except ValueError:
        return False


def is_valid_risk_severity(severity: str) -> bool:
    """Type guard to check if string is valid RiskSeverity."""
    try:
        RiskSeverity(severity)
        return True
    except ValueError:
        return False


# Type-safe data conversion utilities
def sprint_to_dict(sprint: Sprint) -> Dict[str, Any]:
    """Convert Sprint model to dictionary with proper typing."""
    return {
        "id": sprint.id,
        "name": sprint.name,
        "goal": sprint.goal,
        "start_date": sprint.start_date.isoformat(),
        "end_date": sprint.end_date.isoformat(),
        "status": sprint.status,
        "planned_capacity": sprint.planned_capacity,
        "completed_points": sprint.completed_points,
        "velocity": sprint.velocity,
        "team_id": sprint.team_id,
        "created_at": sprint.created_at.isoformat() if sprint.created_at else None,
        "updated_at": sprint.updated_at.isoformat() if sprint.updated_at else None
    }


def validate_sprint_request(data: Dict[str, Any]) -> bool:
    """Validate sprint creation request data."""
    required_fields = ["team_id", "name", "start_date", "end_date"]
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            return False
    
    # Validate types
    if not isinstance(data["team_id"], int):
        return False
    
    if not isinstance(data["name"], str) or len(data["name"].strip()) == 0:
        return False
    
    # Validate dates
    try:
        start_date = date.fromisoformat(data["start_date"])
        end_date = date.fromisoformat(data["end_date"])
        
        if start_date >= end_date:
            return False
            
    except (ValueError, TypeError):
        return False
    
    # Validate optional fields
    if "capacity_points" in data:
        if not isinstance(data["capacity_points"], int) or data["capacity_points"] < 0:
            return False
    
    if "suggested_items" in data:
        if not isinstance(data["suggested_items"], list):
            return False
        
        for item_id in data["suggested_items"]:
            if not isinstance(item_id, int):
                return False
    
    return True


# Export main types for use in other modules
__all__ = [
    "SprintService",
    "SprintStatus",
    "RiskSeverity", 
    "VelocityTrend",
    "ConfidenceLevel",
    "BacklogItemSummary",
    "VelocityMetrics",
    "RiskFactor",
    "RecommendedItem",
    "SprintPlanningResult",
    "CurrentSprintMetrics",
    "CompletionForecast",
    "DailyBurndownPoint",
    "BurndownAnalysis",
    "SprintServiceError",
    "SprintValidationError",
    "SprintNotFoundError",
    "InvalidStatusTransitionError",
    "create_sprint_service",
    "is_valid_sprint_status",
    "is_valid_risk_severity",
    "sprint_to_dict",
    "validate_sprint_request"
]