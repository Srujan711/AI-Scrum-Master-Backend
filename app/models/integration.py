from sqlalchemy import Column, String, Text, Date, ForeignKey, JSON, Boolean, Integer
from .base import BaseModel

class IntegrationLog(BaseModel):
    __tablename__ = "integration_logs"
    
    service_name = Column(String, nullable=False)  # jira, slack, github
    action = Column(String, nullable=False)  # sync, create_ticket, post_message
    status = Column(String, nullable=False)  # success, error, pending
    
    # Request/response data
    request_data = Column(JSON, nullable=True)
    response_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timing
    duration_ms = Column(Integer, nullable=True)
    
    # Foreign keys
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
