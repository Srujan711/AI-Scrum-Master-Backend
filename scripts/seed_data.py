#!/usr/bin/env python3
"""
Seed Data Script for AI Scrum Master

Creates realistic test data for development:
- 2 Teams
- 9 Users (various roles)
- 1 Active Sprint
- 10-15 User Stories
- 20-30 Backlog Items
- 3 days of Standup Notes

Usage:
    python scripts/seed_data.py              # Add seed data
    python scripts/seed_data.py --clear      # Clear all data first
"""
import asyncio
import sys
import os
from datetime import date, timedelta
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session, engine
from app.models.base import Base
from app.models.user import User, Team, TeamMembership
from app.models.sprint import Sprint
from app.models.backlog import BacklogItem
from app.models.standup import StandupSummary
from app.models.standup_note import StandupNote
from app.core.security import hash_password


# ==================== DATA DEFINITIONS ====================

USERS_DATA = [
    # Scrum Masters
    {"email": "alice.sm@company.com", "full_name": "Alice Johnson", "role": "scrum_master", "is_scrum_master": True},
    {"email": "bob.sm@company.com", "full_name": "Bob Martinez", "role": "scrum_master", "is_scrum_master": True},

    # Product Owners
    {"email": "carol.po@company.com", "full_name": "Carol Williams", "role": "product_owner", "is_product_owner": True},
    {"email": "dave.po@company.com", "full_name": "Dave Chen", "role": "product_owner", "is_product_owner": True},

    # Developers
    {"email": "emma.dev@company.com", "full_name": "Emma Rodriguez", "role": "developer"},
    {"email": "frank.dev@company.com", "full_name": "Frank Smith", "role": "developer"},
    {"email": "grace.dev@company.com", "full_name": "Grace Lee", "role": "developer"},
    {"email": "henry.dev@company.com", "full_name": "Henry Brown", "role": "developer"},
    {"email": "ivy.dev@company.com", "full_name": "Ivy Patel", "role": "developer"},
]

TEAMS_DATA = [
    {
        "name": "Product Team",
        "description": "Core product development team",
        "members": ["alice.sm@company.com", "carol.po@company.com", "emma.dev@company.com",
                    "frank.dev@company.com", "grace.dev@company.com"]
    },
    {
        "name": "Platform Team",
        "description": "Infrastructure and platform team",
        "members": ["bob.sm@company.com", "dave.po@company.com", "henry.dev@company.com", "ivy.dev@company.com"]
    }
]

# Backlog items with intentional issues for AI to catch
BACKLOG_ITEMS = [
    # Well-defined stories
    {"title": "User Authentication System", "description": "Implement JWT-based authentication with login, logout, and token refresh. AC: Users can login with email/password, tokens expire after 30min, refresh tokens valid for 7 days.", "priority": "high", "story_points": 8, "status": "done"},
    {"title": "Dashboard Analytics View", "description": "Create dashboard showing key metrics: active users, revenue, conversion rate. AC: Real-time updates, exportable to PDF, mobile responsive.", "priority": "high", "story_points": 5, "status": "done"},
    {"title": "Payment Gateway Integration", "description": "Integrate Stripe for credit card payments. AC: Support Visa/Mastercard/Amex, handle 3D Secure, webhook for payment status.", "priority": "high", "story_points": 8, "status": "in_progress"},
    {"title": "Email Notification System", "description": "Send transactional emails (signup, password reset, order confirmation). AC: Template system, retry logic, delivery tracking.", "priority": "medium", "story_points": 5, "status": "in_progress"},
    {"title": "Search Functionality", "description": "Add full-text search across products. AC: Search by name, description, tags. Results in <500ms, highlight matches.", "priority": "medium", "story_points": 5, "status": "to_do"},

    # Duplicate/Similar stories (AI should flag these)
    {"title": "User Login Feature", "description": "Need a way for users to log into the system", "priority": "medium", "story_points": 3, "status": "to_do"},
    {"title": "Authentication Module", "description": "Build login functionality", "priority": "low", "story_points": 5, "status": "to_do"},

    # Vague stories (need clarification)
    {"title": "Improve Performance", "description": "The app is slow", "priority": "high", "story_points": None, "status": "to_do"},
    {"title": "Fix Bugs", "description": "There are some bugs that need fixing", "priority": "medium", "story_points": None, "status": "to_do"},
    {"title": "Update UI", "description": "Make it look better", "priority": "low", "story_points": None, "status": "to_do"},
    {"title": "Add More Features", "description": "Users want more features", "priority": "medium", "story_points": None, "status": "to_do"},

    # Missing acceptance criteria
    {"title": "Admin Dashboard", "description": "Dashboard for admins to manage users and content", "priority": "high", "story_points": 8, "status": "to_do"},
    {"title": "Social Media Sharing", "description": "Allow users to share content on Facebook, Twitter, LinkedIn", "priority": "low", "story_points": 3, "status": "to_do"},
    {"title": "Export to Excel", "description": "Let users download data as Excel files", "priority": "medium", "story_points": 3, "status": "to_do"},
    {"title": "Mobile App", "description": "Build mobile app for iOS and Android", "priority": "high", "story_points": None, "status": "to_do"},

    # More realistic stories
    {"title": "API Rate Limiting", "description": "Implement rate limiting (100 req/min per user). AC: Return 429 with Retry-After header, configurable limits per endpoint.", "priority": "high", "story_points": 3, "status": "to_do"},
    {"title": "User Profile Page", "description": "Profile page with avatar, bio, social links. AC: Image upload (<2MB), markdown bio, edit/save functionality.", "priority": "medium", "story_points": 5, "status": "to_do"},
    {"title": "Password Reset Flow", "description": "Forgot password with email verification. AC: Token valid 1hr, secure reset link, rate limit attempts.", "priority": "high", "story_points": 3, "status": "in_progress"},
    {"title": "Pagination for Lists", "description": "Add pagination to all list views. AC: Configurable page size (10/25/50), show total count, prev/next buttons.", "priority": "medium", "story_points": 2, "status": "to_do"},
    {"title": "Error Logging System", "description": "Centralized error logging with Sentry. AC: Capture stack traces, user context, alert on critical errors.", "priority": "high", "story_points": 3, "status": "to_do"},
    {"title": "Dark Mode", "description": "Add dark mode theme. AC: Toggle in settings, persist preference, smooth transition.", "priority": "low", "story_points": 5, "status": "to_do"},
    {"title": "CSV Import", "description": "Import users/products from CSV. AC: Validate format, handle duplicates, show progress bar, error report.", "priority": "medium", "story_points": 5, "status": "to_do"},
    {"title": "Two-Factor Authentication", "description": "Optional 2FA using TOTP (Google Authenticator). AC: QR code setup, backup codes, remember device.", "priority": "medium", "story_points": 8, "status": "to_do"},
    {"title": "Audit Log", "description": "Track all user actions for compliance. AC: Log CRUD operations, searchable, retention policy.", "priority": "low", "story_points": 5, "status": "to_do"},
    {"title": "Webhook System", "description": "Allow external services to subscribe to events. AC: Event types, retry logic, signature verification.", "priority": "low", "story_points": 8, "status": "to_do"},
]

# Standup notes for last 3 days
def generate_standup_notes(team_members, sprint_start):
    """Generate realistic standup notes for the past 3 days"""
    notes = []

    # Templates for variety
    completed_tasks = [
        "Completed login API endpoint",
        "Fixed bug in user registration",
        "Implemented OAuth integration",
        "Wrote unit tests for payment module",
        "Deployed hotfix to production",
        "Code review for 3 PRs",
        "Refactored database queries",
        "Updated API documentation",
        "Fixed 2 security vulnerabilities",
        "Optimized image loading",
    ]

    planned_tasks = [
        "Working on password reset flow",
        "Implementing search functionality",
        "Writing integration tests",
        "Refactoring authentication module",
        "Code review for team PRs",
        "Meeting with product team",
        "Debugging production issue",
        "Updating deployment scripts",
        "Performance optimization",
        "Database migration",
    ]

    blockers = [
        "Waiting for design mockups",
        "Need access to production database",
        "Blocked by API rate limits on third-party service",
        "Waiting for code review approval",
        "Infrastructure team needs to provision servers",
        "Clarification needed from product owner",
        "Dependencies not yet merged",
        "CI/CD pipeline is down",
    ]

    for day_offset in range(3):
        day = sprint_start + timedelta(days=day_offset)

        for idx, member in enumerate(team_members):
            # Some variation in who submits
            if day_offset == 0 and idx % 3 == 0:
                continue  # Skip some members on first day

            # Create note
            note = {
                "user_email": member,
                "date": day,
                "completed_yesterday": [
                    completed_tasks[(idx + day_offset * 2) % len(completed_tasks)],
                    completed_tasks[(idx + day_offset * 2 + 1) % len(completed_tasks)]
                ],
                "planned_today": [
                    planned_tasks[(idx + day_offset) % len(planned_tasks)],
                    planned_tasks[(idx + day_offset + 3) % len(planned_tasks)]
                ],
                "blockers": [blockers[(idx + day_offset) % len(blockers)]] if (idx + day_offset) % 4 == 0 else []
            }
            notes.append(note)

    return notes


# ==================== SEED FUNCTIONS ====================

async def clear_all_data(session: AsyncSession):
    """Clear all data from the database"""
    print("🗑️  Clearing existing data...")

    # Delete in correct order (respecting foreign keys)
    await session.execute(delete(StandupNote))
    await session.execute(delete(StandupSummary))
    await session.execute(delete(BacklogItem))
    await session.execute(delete(Sprint))
    await session.execute(delete(TeamMembership))
    await session.execute(delete(Team))
    await session.execute(delete(User))

    await session.commit()
    print("✅ All data cleared")


async def create_users(session: AsyncSession):
    """Create users with hashed passwords"""
    print("\n👥 Creating users...")

    users_map = {}
    for user_data in USERS_DATA:
        user = User(
            email=user_data["email"],
            password_hash=hash_password("password123"),  # All users have same password for dev
            full_name=user_data["full_name"],
            is_scrum_master=user_data.get("is_scrum_master", False),
            is_product_owner=user_data.get("is_product_owner", False),
            is_active=True,
            timezone="UTC"
        )
        session.add(user)
        users_map[user_data["email"]] = user
        print(f"  ✓ Created: {user.full_name} ({user.email}) - Role: {user_data['role']}")

    await session.commit()

    # Refresh to get IDs
    for user in users_map.values():
        await session.refresh(user)

    return users_map


async def create_teams(session: AsyncSession, users_map):
    """Create teams and team memberships"""
    print("\n🏢 Creating teams...")

    teams = []
    for team_data in TEAMS_DATA:
        team = Team(
            name=team_data["name"],
            description=team_data["description"],
            is_active=True,
            standup_time="09:00",
            standup_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
            sprint_length=14,
            ai_enabled=True,
            auto_standup=True
        )
        session.add(team)
        await session.flush()  # Get team ID

        print(f"  ✓ Created team: {team.name}")

        # Add team members
        for member_email in team_data["members"]:
            user = users_map[member_email]

            # Determine role
            role = "developer"
            if user.is_scrum_master:
                role = "scrum_master"
            elif user.is_product_owner:
                role = "product_owner"

            membership = TeamMembership(
                user_id=user.id,
                team_id=team.id,
                role=role,
                is_active=True
            )
            session.add(membership)
            print(f"    - Added {user.full_name} as {role}")

        teams.append(team)

    await session.commit()

    # Refresh teams
    for team in teams:
        await session.refresh(team)

    return teams


async def create_sprint(session: AsyncSession, team):
    """Create an active sprint for the team"""
    print(f"\n🏃 Creating sprint for {team.name}...")

    today = date.today()
    sprint_start = today - timedelta(days=3)  # Started 3 days ago
    sprint_end = sprint_start + timedelta(days=14)

    sprint = Sprint(
        name="Sprint 24",
        goal="Implement core authentication features and improve dashboard performance",
        start_date=sprint_start,
        end_date=sprint_end,
        status="active",
        planned_capacity=40,  # 40 story points
        completed_points=13,  # 13 points done so far
        team_id=team.id
    )
    session.add(sprint)
    await session.flush()
    await session.refresh(sprint)

    print(f"  ✓ Created: {sprint.name}")
    print(f"    Start: {sprint_start}, End: {sprint_end}")
    print(f"    Goal: {sprint.goal}")

    return sprint


async def create_backlog_items(session: AsyncSession, team, sprint, users):
    """Create backlog items with various states"""
    print(f"\n📋 Creating backlog items for {team.name}...")

    items_count = {"done": 0, "in_progress": 0, "to_do": 0}

    for item_data in BACKLOG_ITEMS:
        # Assign items to sprint if in progress or done
        sprint_id = sprint.id if item_data["status"] in ["done", "in_progress"] else None

        # Assign to a developer if in progress or done
        assigned_to = None
        if item_data["status"] in ["done", "in_progress"]:
            dev_users = [u for u in users if not u.is_scrum_master and not u.is_product_owner]
            if dev_users:
                assigned_to = dev_users[len(BACKLOG_ITEMS) % len(dev_users)].id

        item = BacklogItem(
            title=item_data["title"],
            description=item_data["description"],
            status=item_data["status"],
            priority=item_data["priority"],
            story_points=item_data["story_points"],
            team_id=team.id,
            sprint_id=sprint_id,
            assigned_to=assigned_to
        )
        session.add(item)
        items_count[item_data["status"]] += 1

    await session.commit()

    print(f"  ✓ Created {len(BACKLOG_ITEMS)} items:")
    print(f"    - Done: {items_count['done']}")
    print(f"    - In Progress: {items_count['in_progress']}")
    print(f"    - To Do: {items_count['to_do']}")


async def create_standup_notes(session: AsyncSession, team, sprint, users_map):
    """Create standup notes for the past 3 days"""
    print(f"\n📝 Creating standup notes for {team.name}...")

    # Get team member emails
    member_emails = TEAMS_DATA[0]["members"]  # Product Team members are a list of emails

    # Generate notes
    notes_data = generate_standup_notes(member_emails, sprint.start_date)

    for note_data in notes_data:
        user = users_map[note_data["user_email"]]

        note = StandupNote(
            user_id=user.id,
            team_id=team.id,
            sprint_id=sprint.id,
            date=note_data["date"],
            completed_yesterday=note_data["completed_yesterday"],
            planned_today=note_data["planned_today"],
            blockers=note_data["blockers"]
        )
        session.add(note)

    await session.commit()

    print(f"  ✓ Created {len(notes_data)} standup notes over 3 days")
    print(f"    Date range: {sprint.start_date} to {sprint.start_date + timedelta(days=2)}")


# ==================== MAIN ====================

async def seed_database(clear_first: bool = False):
    """Main seed function"""
    print("=" * 60)
    print("🌱 AI Scrum Master - Database Seeding")
    print("=" * 60)

    async with async_session() as session:
        if clear_first:
            await clear_all_data(session)

        # Create all data
        users_map = await create_users(session)
        teams = await create_teams(session, users_map)

        # Focus on Product Team for sprint and backlog
        product_team = teams[0]
        product_team_users = [u for email, u in users_map.items()
                              if email in TEAMS_DATA[0]["members"]]

        sprint = await create_sprint(session, product_team)
        await create_backlog_items(session, product_team, sprint, product_team_users)
        await create_standup_notes(session, product_team, sprint, users_map)

    print("\n" + "=" * 60)
    print("✅ Database seeding complete!")
    print("=" * 60)
    print("\n📊 Summary:")
    print(f"  Users: {len(USERS_DATA)}")
    print(f"  Teams: {len(TEAMS_DATA)}")
    print(f"  Sprints: 1 (active)")
    print(f"  Backlog Items: {len(BACKLOG_ITEMS)}")
    print(f"  Standup Notes: {len(generate_standup_notes(TEAMS_DATA[0]['members'], date.today() - timedelta(days=3)))}")
    print("\n🔑 Login Credentials:")
    print("  Email: Any from the list above")
    print("  Password: password123")
    print("\n💡 Test Users:")
    print("  Scrum Master: alice.sm@company.com")
    print("  Product Owner: carol.po@company.com")
    print("  Developer: emma.dev@company.com")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed AI Scrum Master database")
    parser.add_argument("--clear", action="store_true", help="Clear all data before seeding")
    args = parser.parse_args()

    asyncio.run(seed_database(clear_first=args.clear))