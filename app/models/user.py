from sqlalchemy import Column, String, Boolean, JSON, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from .base import BaseModel


class User(BaseModel):
    __tablename__ = "users"
    
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_scrum_master = Column(Boolean, default=False)
    is_product_owner = Column(Boolean, default=False)
    
    # Preferences and settings
    preferences = Column(JSON, default={})
    timezone = Column(String, default="UTC")
    
    # OAuth tokens (encrypted)
    jira_token = Column(Text, nullable=True)
    slack_token = Column(Text, nullable=True)
    github_token = Column(Text, nullable=True)
    
    # Relationships
    team_memberships = relationship("TeamMembership", back_populates="user")
    created_standups = relationship("StandupSummary", back_populates="creator")


class Team(BaseModel):
    __tablename__ = "teams"
    
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Team settings
    standup_time = Column(String, default="09:00")  # HH:MM format
    standup_days = Column(JSON, default=["monday", "tuesday", "wednesday", "thursday", "friday"])
    sprint_length = Column(Integer, default=14)  # days
    
    # Integration settings
    jira_project_key = Column(String, nullable=True)
    slack_channel_id = Column(String, nullable=True)
    github_repo = Column(String, nullable=True)
    
    # AI settings
    ai_enabled = Column(Boolean, default=True)
    auto_standup = Column(Boolean, default=True)
    auto_backlog_grooming = Column(Boolean, default=False)
    
    # Relationships
    members = relationship("TeamMembership", back_populates="team")
    sprints = relationship("Sprint", back_populates="team")
    backlog_items = relationship("BacklogItem", back_populates="team")
    standups = relationship("StandupSummary", back_populates="team")


class TeamMembership(BaseModel):
    __tablename__ = "team_memberships"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    role = Column(String, default="developer")  # developer, scrum_master, product_owner
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="team_memberships")
    team = relationship("Team", back_populates="members")