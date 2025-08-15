from sqlalchemy import Column, String, Integer, Date, ForeignKey, JSON, Float, Text
from sqlalchemy.orm import relationship
from .base import BaseModel


class Sprint(BaseModel):
    __tablename__ = "sprints"
    
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, default="planning")  # planning, active, completed, cancelled
    
    # Sprint metrics
    planned_capacity = Column(Integer, nullable=True)  # story points
    completed_points = Column(Integer, default=0)
    velocity = Column(Float, nullable=True)
    
    # AI-generated insights
    ai_insights = Column(JSON, default={})
    risk_factors = Column(JSON, default=[])
    
    # Foreign keys
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="sprints")
    backlog_items = relationship("BacklogItem", back_populates="sprint")
    standups = relationship("StandupSummary", back_populates="sprint")
