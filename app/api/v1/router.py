from fastapi import APIRouter
from .backlog import router as backlog_router
from .sprints import router as sprints_router
from .integrations import router as integrations_router

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(backlog_router, prefix="/backlog", tags=["backlog"])
api_router.include_router(sprints_router, prefix="/sprints", tags=["sprints"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])


# api/v1/standups.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date as Date, datetime
from pydantic import BaseModel

from ...database import get_db
from ...core.auth import get_current_user
from ...models.user import User
from ...models.standup import StandupSummary
from ...services.standup_service import StandupService
from ...agents.standup_agent import StandupAgent

router = APIRouter()

# Pydantic models for requests/responses
class StandupRequest(BaseModel):
    team_id: int
    sprint_id: Optional[int] = None
    date: Optional[Date] = None
    manual_input: Optional[dict] = None

class StandupResponse(BaseModel):
    id: int
    date: Date
    summary_text: str
    completed_yesterday: List[str]
    planned_today: List[str]
    blockers: List[str]
    action_items: List[dict]
    ai_generated: bool
    human_approved: bool
    team_id: int
    sprint_id: Optional[int]

class StandupUpdate(BaseModel):
    summary_text: Optional[str] = None
    human_approved: Optional[bool] = None
    action_items: Optional[List[dict]] = None


@router.post("/generate", response_model=StandupResponse)
async def generate_standup_summary(
    request: StandupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate AI-powered standup summary"""
    
    try:
        # Initialize standup service
        standup_service = StandupService(db)
        
        # Generate standup summary
        result = await standup_service.generate_standup_summary(
            team_id=request.team_id,
            sprint_id=request.sprint_id,
            date=request.date or Date.today(),
            creator_id=current_user.id,
            manual_input=request.manual_input
        )
        
        # Schedule background tasks (e.g., post to Slack)
        background_tasks.add_task(
            standup_service.post_to_slack,
            standup_id=result.id
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{standup_id}", response_model=StandupResponse)
async def get_standup(
    standup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific standup summary"""
    
    standup_service = StandupService(db)
    standup = await standup_service.get_standup(standup_id)
    
    if not standup:
        raise HTTPException(status_code=404, detail="Standup not found")
    
    # Check permissions (user should be part of the team)
    if not await standup_service.user_has_access(current_user.id, standup.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return standup


@router.put("/{standup_id}", response_model=StandupResponse)
async def update_standup(
    standup_id: int,
    update_data: StandupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update standup summary (human review/approval)"""
    
    standup_service = StandupService(db)
    
    # Check permissions
    standup = await standup_service.get_standup(standup_id)
    if not standup:
        raise HTTPException(status_code=404, detail="Standup not found")
    
    if not await standup_service.user_has_access(current_user.id, standup.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update standup
    updated_standup = await standup_service.update_standup(
        standup_id=standup_id,
        **update_data.model_dump(exclude_none=True)
    )
    
    return updated_standup


@router.get("/team/{team_id}", response_model=List[StandupResponse])
async def get_team_standups(
    team_id: int,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get standup summaries for a team"""
    
    standup_service = StandupService(db)
    
    # Check permissions
    if not await standup_service.user_has_access(current_user.id, team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    standups = await standup_service.get_team_standups(
        team_id=team_id,
        limit=limit,
        offset=offset
    )
    
    return standups


@router.post("/{standup_id}/approve")
async def approve_standup(
    standup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Approve AI-generated standup summary"""
    
    standup_service = StandupService(db)
    
    # Check permissions (only Scrum Masters can approve)
    standup = await standup_service.get_standup(standup_id)
    if not standup:
        raise HTTPException(status_code=404, detail="Standup not found")
    
    if not current_user.is_scrum_master:
        raise HTTPException(status_code=403, detail="Only Scrum Masters can approve standups")
    
    await standup_service.approve_standup(standup_id, current_user.id)
    
    return {"message": "Standup approved successfully"}


@router.post("/{standup_id}/post-to-slack")
async def post_standup_to_slack(
    standup_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Post standup summary to Slack"""
    
    standup_service = StandupService(db)
    
    # Check permissions
    standup = await standup_service.get_standup(standup_id)
    if not standup:
        raise HTTPException(status_code=404, detail="Standup not found")
    
    if not await standup_service.user_has_access(current_user.id, standup.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Schedule background task
    background_tasks.add_task(
        standup_service.post_to_slack,
        standup_id=standup_id
    )
    
    return {"message": "Standup will be posted to Slack"}
