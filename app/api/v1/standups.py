"""
Standup API Endpoints

Provides endpoints for generating and managing daily standup summaries
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import date as Date, datetime

from pydantic import BaseModel, Field

from ...database import get_db
from ...models.standup import StandupSummary
from ...models.user import User, Team, TeamMembership
from ...agents.standup_agent import StandupAgent

router = APIRouter()


# Pydantic models for requests/responses
class StandupGenerateRequest(BaseModel):
    """Request to generate a standup summary"""
    team_id: int = Field(..., description="ID of the team")
    date: Optional[Date] = Field(None, description="Date for the standup (defaults to today)")


class StandupResponse(BaseModel):
    """Standup summary response"""
    id: int
    date: Date
    summary_text: str
    completed_yesterday: List[str]
    planned_today: List[str]
    blockers: List[str]
    action_items: List[dict]
    risk_indicators: List[str]
    sentiment_score: float
    ai_generated: bool
    human_approved: bool
    team_id: int
    sprint_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class StandupListResponse(BaseModel):
    """List of standup summaries"""
    standups: List[StandupResponse]
    total: int


@router.post("/generate", response_model=dict, status_code=201)
async def generate_standup_summary(
    request: StandupGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate AI-powered standup summary for a team

    This endpoint:
    1. Fetches standup notes from team members for the specified date
    2. Uses AI (Ollama/LLM) to generate a comprehensive summary
    3. Saves the summary to the database
    4. Returns the generated summary with metadata
    """

    try:
        # Initialize standup agent
        agent = StandupAgent()

        # Generate standup summary
        result = await agent.execute(
            team_id=request.team_id,
            target_date=request.date or Date.today(),
            db_session=db
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to generate standup summary")
            )

        return {
            "message": "Standup summary generated successfully",
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{standup_id}", response_model=StandupResponse)
async def get_standup_summary(
    standup_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific standup summary by ID"""

    stmt = select(StandupSummary).where(StandupSummary.id == standup_id)
    result = await db.execute(stmt)
    standup = result.scalar_one_or_none()

    if not standup:
        raise HTTPException(status_code=404, detail="Standup summary not found")

    return standup


@router.get("/team/{team_id}", response_model=StandupListResponse)
async def get_team_standups(
    team_id: int,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Get standup summaries for a specific team"""

    # Verify team exists
    team_stmt = select(Team).where(Team.id == team_id)
    team_result = await db.execute(team_stmt)
    team = team_result.scalar_one_or_none()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get standups
    stmt = select(StandupSummary).where(
        StandupSummary.team_id == team_id
    ).order_by(StandupSummary.date.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    standups = result.scalars().all()

    # Get total count
    count_stmt = select(StandupSummary).where(StandupSummary.team_id == team_id)
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    return {
        "standups": standups,
        "total": total
    }


@router.get("/team/{team_id}/date/{date}", response_model=StandupResponse)
async def get_team_standup_by_date(
    team_id: int,
    date: Date,
    db: AsyncSession = Depends(get_db)
):
    """Get standup summary for a specific team and date"""

    stmt = select(StandupSummary).where(
        StandupSummary.team_id == team_id,
        StandupSummary.date == date
    )
    result = await db.execute(stmt)
    standup = result.scalar_one_or_none()

    if not standup:
        raise HTTPException(
            status_code=404,
            detail=f"No standup summary found for team {team_id} on {date}"
        )

    return standup


@router.post("/{standup_id}/approve", response_model=dict)
async def approve_standup(
    standup_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Approve an AI-generated standup summary

    Note: In a real implementation, this would check user permissions
    """

    stmt = select(StandupSummary).where(StandupSummary.id == standup_id)
    result = await db.execute(stmt)
    standup = result.scalar_one_or_none()

    if not standup:
        raise HTTPException(status_code=404, detail="Standup summary not found")

    standup.human_approved = True
    await db.commit()
    await db.refresh(standup)

    return {
        "message": "Standup summary approved successfully",
        "standup_id": standup_id
    }


@router.delete("/{standup_id}", response_model=dict)
async def delete_standup(
    standup_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a standup summary"""

    stmt = select(StandupSummary).where(StandupSummary.id == standup_id)
    result = await db.execute(stmt)
    standup = result.scalar_one_or_none()

    if not standup:
        raise HTTPException(status_code=404, detail="Standup summary not found")

    await db.delete(standup)
    await db.commit()

    return {
        "message": "Standup summary deleted successfully",
        "standup_id": standup_id
    }