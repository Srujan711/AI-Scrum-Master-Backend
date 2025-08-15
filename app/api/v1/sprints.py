from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

from ...database import get_db
from ...core.auth import get_current_user
from ...models.user import User
from ...models.sprint import Sprint
from ...services.sprint_service import SprintService

router = APIRouter()

class SprintPlanningRequest(BaseModel):
    team_id: int
    sprint_name: str
    start_date: date
    end_date: date
    capacity_points: Optional[int] = None
    suggested_items: Optional[List[int]] = None

class SprintResponse(BaseModel):
    id: int
    name: str
    goal: Optional[str]
    start_date: date
    end_date: date
    status: str
    planned_capacity: Optional[int]
    completed_points: int
    velocity: Optional[float]
    ai_insights: dict
    risk_factors: List[str]
    team_id: int

class SprintPlanningResponse(BaseModel):
    recommended_items: List[dict]
    capacity_analysis: dict
    risk_assessment: List[dict]
    suggested_goal: str
    velocity_forecast: float


@router.post("/plan", response_model=SprintPlanningResponse)
async def plan_sprint(
    request: SprintPlanningRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate AI-powered sprint planning recommendations"""
    
    sprint_service = SprintService(db)
    
    # Check permissions
    if not await sprint_service.user_has_access(current_user.id, request.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Generate sprint plan
    planning_result = await sprint_service.generate_sprint_plan(
        team_id=request.team_id,
        capacity_points=request.capacity_points,
        start_date=request.start_date,
        end_date=request.end_date,
        user_id=current_user.id
    )
    
    return planning_result


@router.post("/create", response_model=SprintResponse)
async def create_sprint(
    request: SprintPlanningRequest,
    apply_ai_suggestions: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new sprint with optional AI recommendations"""
    
    sprint_service = SprintService(db)
    
    # Check permissions (only Scrum Masters can create sprints)
    if not current_user.is_scrum_master:
        raise HTTPException(status_code=403, detail="Only Scrum Masters can create sprints")
    
    if not await sprint_service.user_has_access(current_user.id, request.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create sprint
    sprint = await sprint_service.create_sprint(
        team_id=request.team_id,
        name=request.sprint_name,
        start_date=request.start_date,
        end_date=request.end_date,
        capacity_points=request.capacity_points,
        suggested_items=request.suggested_items if apply_ai_suggestions else None,
        creator_id=current_user.id
    )
    
    return sprint


@router.get("/{sprint_id}", response_model=SprintResponse)
async def get_sprint(
    sprint_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get sprint details"""
    
    sprint_service = SprintService(db)
    sprint = await sprint_service.get_sprint(sprint_id)
    
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    
    # Check permissions
    if not await sprint_service.user_has_access(current_user.id, sprint.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return sprint


@router.get("/{sprint_id}/burndown")
async def get_sprint_burndown(
    sprint_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get burndown chart data for sprint"""
    
    sprint_service = SprintService(db)
    
    # Check permissions
    sprint = await sprint_service.get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    
    if not await sprint_service.user_has_access(current_user.id, sprint.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    burndown_data = await sprint_service.generate_burndown_data(sprint_id)
    
    return burndown_data


@router.get("/team/{team_id}", response_model=List[SprintResponse])
async def get_team_sprints(
    team_id: int,
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get sprints for a team"""
    
    sprint_service = SprintService(db)
    
    # Check permissions
    if not await sprint_service.user_has_access(current_user.id, team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    sprints = await sprint_service.get_team_sprints(
        team_id=team_id,
        status=status,
        limit=limit,
        offset=offset
    )
    
    return sprints