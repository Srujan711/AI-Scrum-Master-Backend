from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel

from ...database import get_db
from ...core.auth import get_current_user
from ...models.user import User
from ...models.backlog import BacklogItem
from ...services.backlog_service import BacklogService

router = APIRouter()

class BacklogAnalysisRequest(BaseModel):
    team_id: int
    item_ids: Optional[List[int]] = None
    auto_apply_suggestions: bool = False

class BacklogItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    story_points: Optional[int]
    ai_suggestions: dict
    clarity_score: Optional[float]
    similar_items: List[int]

class BacklogAnalysisResponse(BaseModel):
    team_id: int
    items_analyzed: int
    analysis_results: List[dict]
    duplicate_groups: List[dict]
    prioritization_suggestions: List[dict]
    generated_at: str


@router.post("/analyze", response_model=BacklogAnalysisResponse)
async def analyze_backlog(
    request: BacklogAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Run AI analysis on backlog items"""
    
    backlog_service = BacklogService(db)
    
    # Check permissions
    if not await backlog_service.user_has_access(current_user.id, request.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Run analysis
    result = await backlog_service.analyze_backlog(
        team_id=request.team_id,
        item_ids=request.item_ids,
        user_id=current_user.id
    )
    
    # Auto-apply suggestions if requested
    if request.auto_apply_suggestions:
        background_tasks.add_task(
            backlog_service.apply_suggestions,
            analysis_result=result,
            user_id=current_user.id
        )
    
    return result


@router.get("/team/{team_id}", response_model=List[BacklogItemResponse])
async def get_team_backlog(
    team_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get backlog items for a team"""
    
    backlog_service = BacklogService(db)
    
    # Check permissions
    if not await backlog_service.user_has_access(current_user.id, team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    items = await backlog_service.get_team_backlog(
        team_id=team_id,
        status=status,
        priority=priority,
        limit=limit,
        offset=offset
    )
    
    return items


@router.put("/{item_id}/apply-suggestions")
async def apply_ai_suggestions(
    item_id: int,
    suggestions_to_apply: List[str],  # e.g., ["description", "acceptance_criteria"]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Apply AI suggestions to a backlog item"""
    
    backlog_service = BacklogService(db)
    
    # Get item and check permissions
    item = await backlog_service.get_backlog_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    
    if not await backlog_service.user_has_access(current_user.id, item.team_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Apply suggestions
    updated_item = await backlog_service.apply_ai_suggestions(
        item_id=item_id,
        suggestions_to_apply=suggestions_to_apply,
        user_id=current_user.id
    )
    
    return updated_item
