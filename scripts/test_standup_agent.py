#!/usr/bin/env python3
"""
Test script for StandupAgent

Tests the standup agent with real seeded data from the database.
"""

import asyncio
import sys
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.standup_agent import StandupAgent
from app.database import async_session
from sqlalchemy import select
from app.models.standup_note import StandupNote
# Import all models to ensure SQLAlchemy can resolve relationships
from app.models.user import User, Team, TeamMembership
from app.models.sprint import Sprint
from app.models.backlog import BacklogItem
from app.models.standup import StandupSummary
from app.models.ai_operation import AIOperation
from app.models.integration import IntegrationLog


async def test_standup_agent():
    """Test the standup agent with seeded data"""

    print("=" * 60)
    print("Testing Standup Agent")
    print("=" * 60)

    # Initialize agent
    agent = StandupAgent()

    # Check what dates we have standup notes for
    async with async_session() as session:
        stmt = select(StandupNote.date, StandupNote.team_id).distinct()
        result = await session.execute(stmt)
        available_dates = result.all()

        print(f"\n📅 Available standup note dates:")
        for note_date, team_id in available_dates:
            print(f"  - Team {team_id}: {note_date}")

    if not available_dates:
        print("\n❌ No standup notes found in database!")
        print("   Run 'python3 scripts/seed_data.py' first")
        return

    # Use the first available date and team
    test_date, test_team_id = available_dates[0]

    print(f"\n🤖 Generating standup summary for Team {test_team_id} on {test_date}")
    print("-" * 60)

    try:
        # Execute the agent
        result = await agent.execute(
            team_id=test_team_id,
            target_date=test_date
        )

        if result.get("success"):
            print("\n✅ Standup Summary Generated Successfully!")
            print("=" * 60)
            print(f"\n{result['summary_text']}")
            print("\n" + "=" * 60)
            print(f"\n📊 Metadata:")
            print(f"  - Summary ID: {result['summary_id']}")
            print(f"  - Date: {result['date']}")
            print(f"  - Team ID: {result['team_id']}")
            print(f"  - Tokens Used: {result['tokens_used']}")
            print(f"  - Cost: ${result['cost_usd']:.4f}")
            print(f"  - Generated At: {result['generated_at']}")

            if result.get('action_items'):
                print(f"\n🎯 Action Items ({len(result['action_items'])}):")
                for item in result['action_items']:
                    print(f"  - [{item.get('priority', 'N/A').upper()}] {item.get('description')}")
                    if item.get('assignee'):
                        print(f"    Assignee: {item['assignee']}")

            if result.get('risk_indicators'):
                print(f"\n⚠️  Risk Indicators:")
                for risk in result['risk_indicators']:
                    print(f"  - {risk}")
        else:
            print(f"\n❌ Error: {result.get('error')}")

    except Exception as e:
        print(f"\n❌ Error executing standup agent: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_standup_agent())