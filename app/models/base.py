from sqlalchemy import Column, Integer, DateTime, String, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

Base = declarative_base()


class BaseModel(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }