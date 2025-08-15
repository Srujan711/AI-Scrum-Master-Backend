from sqlalchemy import Column, String, Integer, Text, Date, ForeignKey, JSON, Boolean, Float
from sqlalchemy.orm import relationship
from .base import BaseModel


class StandupSummary(BaseModel):
    __tablename__ = "standup_summaries"
    
    date = Column(Date, nullable=False)
    summary_text = Column(Text, nullable=False)
    
    # Structured data
    completed_yesterday = Column(JSON, default=[])
    planned_today = Column(JSON, default=[])
    blockers = Column(JSON, default=[])
    absent_members = Column(JSON, default=[])
    
    # AI analysis
    ai_generated = Column(Boolean, default=True)
    sentiment_score = Column(Float, nullable=True)
    risk_indicators = Column(JSON, default=[])
    action_items = Column(JSON, default=[])
    
    # Status
    posted_to_slack = Column(Boolean, default=False)
    human_approved = Column(Boolean, default=False)
    
    # Foreign keys
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="standups")
    sprint = relationship("Sprint", back_populates="standups")
    creator = relationship("User", back_populates="created_standups")
