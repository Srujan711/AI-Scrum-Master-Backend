#!/usr/bin/env python3
"""
Initialize database with all tables
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.models.base import Base

# Import all models so they're registered
from app.models.user import User, Team, TeamMembership
from app.models.sprint import Sprint
from app.models.backlog import BacklogItem
from app.models.standup import StandupSummary
from app.models.standup_note import StandupNote
from app.models.ai_operation import AIOperation
from app.models.integration import IntegrationLog


async def init_database():
    """Create all tables"""
    print("🗄️  Initializing database...")
    print(f"Creating tables: {', '.join([t.name for t in Base.metadata.sorted_tables])}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("✅ Database initialized successfully!")


if __name__ == "__main__":
    asyncio.run(init_database())