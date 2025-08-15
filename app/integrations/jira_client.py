from __future__ import annotations

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import json

from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession
from atlassian import Jira as AtlassianJira

from .base import (
    BaseIntegration, 
    IntegrationConfig, 
    IntegrationCredentials,
    IntegrationStatus,
    AuthenticationError,
    ValidationError,
    IntegrationError
)

# Jira-specific models
class JiraConfig(IntegrationConfig):
    """Jira integration configuration."""
    
    name: str = "jira"
    server_url: str = Field(..., description="Jira server URL")
    username: Optional[str] = None
    api_token: Optional[str] = None
    cloud: bool = Field(default=True, description="Is Jira Cloud instance")
    
    @validator('server_url')
    def validate_server_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Server URL must start with http:// or https://')
        return v.rstrip('/')

class JiraIssue(BaseModel):
    """Jira issue representation."""
    
    key: str
    id: str
    summary: str
    description: Optional[str] = None
    issue_type: str
    status: str
    priority: str
    assignee: Optional[str] = None
    reporter: str
    created: datetime
    updated: datetime
    story_points: Optional[int] = None
    sprint_id: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)

class JiraSprint(BaseModel):
    """Jira sprint representation."""
    
    id: str
    name: str
    state: str  # future, active, closed
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    complete_date: Optional[datetime] = None
    board_id: str
    goal: Optional[str] = None

class JiraProject(BaseModel):
    """Jira project representation."""
    
    key: str
    id: str
    name: str
    description: Optional[str] = None
    lead: Optional[str] = None
    project_type: str
    url: str

class JiraError(IntegrationError):
    """Jira-specific error."""
    pass


class JiraClient(BaseIntegration[JiraConfig]):
    """
    Production-ready Jira integration client.
    
    Features:
    - Issue management (CRUD)
    - Sprint operations
    - Project management
    - Search and filtering
    - Bulk operations
    - Webhook support
    """
    
    def __init__(
        self,
        config: JiraConfig,
        credentials: Optional[IntegrationCredentials] = None,
        db: Optional[AsyncSession] = None
    ) -> None:
        super().__init__(config, credentials, db)
        self._jira_client: Optional[AtlassianJira] = None
    
    async def connect(self) -> None:
        """Connect to Jira instance."""
        self._logger.info("Connecting to Jira at %s", self.config.server_url)
        
        try:
            if self.credentials:
                # OAuth connection
                self._jira_client = AtlassianJira(
                    url=self.config.server_url,
                    token=self.credentials.access_token,
                    cloud=self.config.cloud
                )
            elif self.config.username and self.config.api_token:
                # Basic auth connection
                self._jira_client = AtlassianJira(
                    url=self.config.server_url,
                    username=self.config.username,
                    password=self.config.api_token,
                    cloud=self.config.cloud
                )
            else:
                raise AuthenticationError(
                    "No valid authentication method provided",
                    self.config.name
                )
            
            # Test connection
            await self.test_connection()
            self.status = IntegrationStatus.CONNECTED
            self._logger.info("Successfully connected to Jira")
            
        except Exception as e:
            self.status = IntegrationStatus.ERROR
            self._logger.error("Failed to connect to Jira: %s", str(e))
            raise JiraError(
                f"Connection failed: {str(e)}",
                self.config.name
            ) from e
    
    async def disconnect(self) -> None:
        """Disconnect from Jira."""
        self._jira_client = None
        self.status = IntegrationStatus.DISCONNECTED
        await self.close()
        self._logger.info("Disconnected from Jira")
    
    async def test_connection(self) -> bool:
        """Test Jira connection."""
        if not self._jira_client:
            return False
        
        try:
            # Test with a simple API call
            myself = self._jira_client.myself()
            self._logger.debug("Connection test successful, user: %s", myself.get('displayName'))
            return True
        except Exception as e:
            self._logger.error("Connection test failed: %s", str(e))
            return False
    
    async def refresh_credentials(self) -> None:
        """Refresh OAuth credentials."""
        if not self.credentials or not self.credentials.refresh_token:
            raise AuthenticationError(
                "No refresh token available",
                self.config.name
            )
        
        # OAuth refresh logic would go here
        # This depends on your OAuth implementation
        self._logger.info("Refreshing Jira credentials")
        
        # Update credentials and reconnect
        await self.connect()
    
    # Issue operations
    
    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Get issue by key."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            issue_data = self._jira_client.issue(issue_key)
            return self._parse_issue(issue_data)
        except Exception as e:
            raise JiraError(
                f"Failed to get issue {issue_key}: {str(e)}",
                self.config.name
            ) from e
    
    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: Optional[str] = None,
        issue_type: str = "Story",
        priority: str = "Medium",
        assignee: Optional[str] = None,
        **kwargs
    ) -> JiraIssue:
        """Create new issue."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        issue_dict = {
            "project": {"key": project_key},
            "summary": summary,
            "description": description or "",
            "issuetype": {"name": issue_type},
            "priority": {"name": priority}
        }
        
        if assignee:
            issue_dict["assignee"] = {"name": assignee}
        
        # Add custom fields
        issue_dict.update(kwargs)
        
        try:
            new_issue = self._jira_client.create_issue(fields=issue_dict)
            return await self.get_issue(new_issue["key"])
        except Exception as e:
            raise JiraError(
                f"Failed to create issue: {str(e)}",
                self.config.name
            ) from e
    
    async def update_issue(
        self,
        issue_key: str,
        fields: Dict[str, Any]
    ) -> JiraIssue:
        """Update issue fields."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            self._jira_client.update_issue_field(issue_key, fields)
            return await self.get_issue(issue_key)
        except Exception as e:
            raise JiraError(
                f"Failed to update issue {issue_key}: {str(e)}",
                self.config.name
            ) from e
    
    async def transition_issue(
        self,
        issue_key: str,
        transition: str
    ) -> JiraIssue:
        """Transition issue status."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            self._jira_client.transition_issue(issue_key, transition)
            return await self.get_issue(issue_key)
        except Exception as e:
            raise JiraError(
                f"Failed to transition issue {issue_key}: {str(e)}",
                self.config.name
            ) from e
    
    async def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[List[str]] = None
    ) -> List[JiraIssue]:
        """Search issues using JQL."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            search_results = self._jira_client.jql(
                jql=jql,
                limit=max_results,
                start=start_at,
                fields=fields or ["*all"]
            )
            
            issues = []
            for issue_data in search_results.get("issues", []):
                issues.append(self._parse_issue(issue_data))
            
            return issues
        except Exception as e:
            raise JiraError(
                f"Failed to search issues: {str(e)}",
                self.config.name
            ) from e
    
    # Sprint operations
    
    async def get_sprint(self, sprint_id: str) -> JiraSprint:
        """Get sprint by ID."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            sprint_data = self._jira_client.sprint(sprint_id)
            return self._parse_sprint(sprint_data)
        except Exception as e:
            raise JiraError(
                f"Failed to get sprint {sprint_id}: {str(e)}",
                self.config.name
            ) from e
    
    async def get_board_sprints(
        self,
        board_id: str,
        state: Optional[str] = None
    ) -> List[JiraSprint]:
        """Get sprints for a board."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            sprints_data = self._jira_client.sprints(board_id, state=state)
            
            sprints = []
            for sprint_data in sprints_data.get("values", []):
                sprints.append(self._parse_sprint(sprint_data))
            
            return sprints
        except Exception as e:
            raise JiraError(
                f"Failed to get sprints for board {board_id}: {str(e)}",
                self.config.name
            ) from e
    
    async def get_sprint_issues(
        self,
        sprint_id: str,
        fields: Optional[List[str]] = None
    ) -> List[JiraIssue]:
        """Get issues in a sprint."""
        jql = f"sprint = {sprint_id}"
        return await self.search_issues(jql, fields=fields)
    
    async def add_issues_to_sprint(
        self,
        sprint_id: str,
        issue_keys: List[str]
    ) -> bool:
        """Add issues to sprint."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            self._jira_client.add_issues_to_sprint(sprint_id, issue_keys)
            return True
        except Exception as e:
            raise JiraError(
                f"Failed to add issues to sprint {sprint_id}: {str(e)}",
                self.config.name
            ) from e
    
    # Project operations
    
    async def get_project(self, project_key: str) -> JiraProject:
        """Get project by key."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            project_data = self._jira_client.project(project_key)
            return self._parse_project(project_data)
        except Exception as e:
            raise JiraError(
                f"Failed to get project {project_key}: {str(e)}",
                self.config.name
            ) from e
    
    async def get_projects(self) -> List[JiraProject]:
        """Get all projects."""
        if not self._jira_client:
            raise JiraError("Not connected to Jira", self.config.name)
        
        try:
            projects_data = self._jira_client.projects()
            
            projects = []
            for project_data in projects_data:
                projects.append(self._parse_project(project_data))
            
            return projects
        except Exception as e:
            raise JiraError(
                f"Failed to get projects: {str(e)}",
                self.config.name
            ) from e
    
    # Bulk operations for AI Scrum Master
    
    async def get_team_daily_updates(
        self,
        project_key: str,
        date: date,
        assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get daily updates for team members."""
        
        # Build JQL for issues updated yesterday
        yesterday = date - timedelta(days=1)
        jql_parts = [
            f"project = {project_key}",
            f"updated >= '{yesterday.isoformat()}' AND updated < '{date.isoformat()}'"
        ]
        
        if assignees:
            assignee_list = ", ".join(f'"{assignee}"' for assignee in assignees)
            jql_parts.append(f"assignee in ({assignee_list})")
        
        jql = " AND ".join(jql_parts)
        
        try:
            issues = await self.search_issues(jql, max_results=100)
            
            # Group by status changes
            completed = [issue for issue in issues if issue.status.lower() in ["done", "closed", "resolved"]]
            in_progress = [issue for issue in issues if issue.status.lower() in ["in progress", "in review"]]
            blocked = [issue for issue in issues if issue.status.lower() in ["blocked", "impediment"]]
            
            return {
                "date": date.isoformat(),
                "project": project_key,
                "completed_issues": [{"key": issue.key, "summary": issue.summary} for issue in completed],
                "in_progress_issues": [{"key": issue.key, "summary": issue.summary} for issue in in_progress],
                "blocked_issues": [{"key": issue.key, "summary": issue.summary} for issue in blocked],
                "total_updates": len(issues)
            }
            
        except Exception as e:
            raise JiraError(
                f"Failed to get daily updates: {str(e)}",
                self.config.name
            ) from e
    
    async def get_sprint_progress(self, sprint_id: str) -> Dict[str, Any]:
        """Get comprehensive sprint progress data."""
        
        try:
            sprint = await self.get_sprint(sprint_id)
            issues = await self.get_sprint_issues(sprint_id)
            
            # Calculate progress metrics
            total_issues = len(issues)
            total_points = sum(issue.story_points or 0 for issue in issues)
            
            completed_issues = [issue for issue in issues if issue.status.lower() in ["done", "closed", "resolved"]]
            completed_points = sum(issue.story_points or 0 for issue in completed_issues)
            
            in_progress_issues = [issue for issue in issues if issue.status.lower() in ["in progress", "in review"]]
            blocked_issues = [issue for issue in issues if issue.status.lower() in ["blocked", "impediment"]]
            
            return {
                "sprint": {
                    "id": sprint.id,
                    "name": sprint.name,
                    "state": sprint.state,
                    "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
                    "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
                    "goal": sprint.goal
                },
                "progress": {
                    "total_issues": total_issues,
                    "completed_issues": len(completed_issues),
                    "in_progress_issues": len(in_progress_issues),
                    "blocked_issues": len(blocked_issues),
                    "total_story_points": total_points,
                    "completed_story_points": completed_points,
                    "completion_percentage": (completed_points / total_points * 100) if total_points > 0 else 0
                },
                "issues": {
                    "completed": [{"key": issue.key, "summary": issue.summary, "points": issue.story_points} for issue in completed_issues],
                    "in_progress": [{"key": issue.key, "summary": issue.summary, "points": issue.story_points} for issue in in_progress_issues],
                    "blocked": [{"key": issue.key, "summary": issue.summary, "points": issue.story_points} for issue in blocked_issues]
                }
            }
            
        except Exception as e:
            raise JiraError(
                f"Failed to get sprint progress: {str(e)}",
                self.config.name
            ) from e
    
    async def create_story_from_ai_suggestion(
        self,
        project_key: str,
        title: str,
        description: str,
        acceptance_criteria: List[str],
        story_points: Optional[int] = None,
        assignee: Optional[str] = None
    ) -> JiraIssue:
        """Create user story from AI suggestion."""
        
        # Format description with acceptance criteria
        formatted_description = f"{description}\n\n*Acceptance Criteria:*\n"
        for i, criteria in enumerate(acceptance_criteria, 1):
            formatted_description += f"{i}. {criteria}\n"
        
        fields = {
            "summary": title,
            "description": formatted_description,
            "issuetype": {"name": "Story"},
            "priority": {"name": "Medium"}
        }
        
        if story_points:
            # Add story points field (field name varies by Jira configuration)
            fields["customfield_10016"] = story_points  # Common story points field
        
        if assignee:
            fields["assignee"] = {"name": assignee}
        
        try:
            return await self.create_issue(project_key, title, formatted_description, **fields)
        except Exception as e:
            raise JiraError(
                f"Failed to create AI-suggested story: {str(e)}",
                self.config.name
            ) from e
    
    # Helper methods
    
    def _parse_issue(self, issue_data: Dict[str, Any]) -> JiraIssue:
        """Parse Jira issue data into JiraIssue model."""
        fields = issue_data.get("fields", {})
        
        return JiraIssue(
            key=issue_data["key"],
            id=issue_data["id"],
            summary=fields.get("summary", ""),
            description=fields.get("description", ""),
            issue_type=fields.get("issuetype", {}).get("name", ""),
            status=fields.get("status", {}).get("name", ""),
            priority=fields.get("priority", {}).get("name", ""),
            assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            reporter=fields.get("reporter", {}).get("displayName", ""),
            created=datetime.fromisoformat(fields.get("created", "").replace("Z", "+00:00")),
            updated=datetime.fromisoformat(fields.get("updated", "").replace("Z", "+00:00")),
            story_points=fields.get("customfield_10016"),  # Common story points field
            sprint_id=self._extract_sprint_id(fields.get("customfield_10020")),  # Common sprint field
            labels=fields.get("labels", []),
            components=[comp["name"] for comp in fields.get("components", [])]
        )
    
    def _parse_sprint(self, sprint_data: Dict[str, Any]) -> JiraSprint:
        """Parse Jira sprint data into JiraSprint model."""
        return JiraSprint(
            id=str(sprint_data["id"]),
            name=sprint_data.get("name", ""),
            state=sprint_data.get("state", ""),
            start_date=datetime.fromisoformat(sprint_data["startDate"].replace("Z", "+00:00")) if sprint_data.get("startDate") else None,
            end_date=datetime.fromisoformat(sprint_data["endDate"].replace("Z", "+00:00")) if sprint_data.get("endDate") else None,
            complete_date=datetime.fromisoformat(sprint_data["completeDate"].replace("Z", "+00:00")) if sprint_data.get("completeDate") else None,
            board_id=str(sprint_data.get("originBoardId", "")),
            goal=sprint_data.get("goal")
        )
    
    def _parse_project(self, project_data: Dict[str, Any]) -> JiraProject:
        """Parse Jira project data into JiraProject model."""
        return JiraProject(
            key=project_data["key"],
            id=project_data["id"],
            name=project_data.get("name", ""),
            description=project_data.get("description", ""),
            lead=project_data.get("lead", {}).get("displayName"),
            project_type=project_data.get("projectTypeKey", ""),
            url=project_data.get("self", "")
        )
    
    def _extract_sprint_id(self, sprint_field: Any) -> Optional[str]:
        """Extract sprint ID from sprint field."""
        if not sprint_field:
            return None
        
        if isinstance(sprint_field, list) and sprint_field:
            # Sprint field is often a list, take the first active sprint
            for sprint in sprint_field:
                if isinstance(sprint, str) and "id=" in sprint:
                    # Parse sprint string format
                    parts = sprint.split(",")
                    for part in parts:
                        if part.strip().startswith("id="):
                            return part.split("=")[1]
        
        return None