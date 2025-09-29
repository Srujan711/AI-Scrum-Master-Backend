from sqlalchemy import Column, Integer, Text, Date, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import BaseModel


class StandupNote(BaseModel):
    """Individual standup notes from team members - raw input before AI summarization"""
    __tablename__ = "standup_notes"

    date = Column(Date, nullable=False)

    # What the team member worked on
    completed_yesterday = Column(JSON, default=[])  # List of completed tasks
    planned_today = Column(JSON, default=[])  # List of planned tasks
    blockers = Column(JSON, default=[])  # List of blockers

    # Raw notes (optional - if submitted as text rather than structured)
    notes = Column(Text, nullable=True)

    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=True)

    # Relationships
    user = relationship("User")
    team = relationship("Team")
    sprint = relationship("Sprint")