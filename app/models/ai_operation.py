from sqlalchemy import Column, String, Integer, Text, Date, ForeignKey, JSON, Boolean, Float
from .base import BaseModel


class AIOperation(BaseModel):
    __tablename__ = "ai_operations"
    
    operation_type = Column(String, nullable=False)  # standup_summary, backlog_analysis, sprint_planning
    model_used = Column(String, nullable=False)
    prompt_template = Column(Text, nullable=False)
    
    # Input/output
    input_data = Column(JSON, nullable=False)
    output_data = Column(JSON, nullable=False)
    confidence_score = Column(Float, nullable=True)
    
    # Performance metrics
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    
    # Human feedback
    human_rating = Column(Integer, nullable=True)  # 1-5 scale
    human_feedback = Column(Text, nullable=True)
    
    # Foreign keys
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)