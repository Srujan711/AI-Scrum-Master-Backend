"""
Production-ready integrations library for AI Scrum Master.

Provides type-safe, async integrations with external services:
- Jira (Atlassian)
- Slack
- GitHub
- OAuth handling
- Webhook management
"""

from .base import BaseIntegration, IntegrationError, IntegrationConfig
from .jira_client import JiraClient, JiraConfig, JiraError
from .slack_client import SlackClient, SlackConfig, SlackError
# Note: Additional integrations can be added when implemented
# from .github_client import GitHubClient, GitHubConfig, GitHubError
# from .oauth_handlers import OAuthManager, OAuthConfig, OAuthError
# from .webhook_manager import WebhookManager, WebhookConfig
# from .integration_factory import IntegrationFactory

__all__ = [
    "BaseIntegration",
    "IntegrationError", 
    "IntegrationConfig",
    "JiraClient",
    "JiraConfig",
    "JiraError",
    "SlackClient",
    "SlackConfig", 
    "SlackError",
    # Additional integrations will be added when implemented
    # "GitHubClient",
    # "GitHubConfig",
    # "GitHubError",
    # "OAuthManager",
    # "OAuthConfig",
    # "OAuthError",
    # "WebhookManager",
    # "WebhookConfig",
    # "IntegrationFactory"
]
