from sqlalchemy import Column, String, Integer, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from .base import BaseModel


class BacklogItem(BaseModel):
    __tablename__ = "backlog_items"
    
    # Core fields
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="to_do")  # to_do, in_progress, done, blocked
    priority = Column(String, default="medium")  # low, medium, high, critical
    story_points = Column(Integer, nullable=True)
    
    # External IDs
    jira_key = Column(String, nullable=True, unique=True)
    trello_card_id = Column(String, nullable=True, unique=True)
    
    # AI analysis
    ai_suggestions = Column(JSON, default={})
    clarity_score = Column(Float, nullable=True)  # 0.0 to 1.0
    complexity_estimate = Column(Integer, nullable=True)
    similar_items = Column(JSON, default=[])  # IDs of similar items
    
    # Relationships
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    team = relationship("Team", back_populates="backlog_items")
    sprint = relationship("Sprint", back_populates="backlog_items")
    assignee = relationship("User")