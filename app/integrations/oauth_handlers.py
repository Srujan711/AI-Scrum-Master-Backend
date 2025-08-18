from typing import Dict, Any, Optional
import httpx
import secrets
import base64
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import json

from ..config import settings
from ..models.user import User
from .base import IntegrationError, AuthenticationError


class OAuthHandlers:
    """Handles OAuth flows for various integrations."""
    
    def __init__(self):
        self.client_configs = {
            "jira": {
                "client_id": settings.jira_client_id,
                "client_secret": settings.jira_client_secret,
                "auth_url": f"{settings.jira_server_url}/rest/oauth2/latest/authorize" if settings.jira_server_url else None,
                "token_url": f"{settings.jira_server_url}/rest/oauth2/latest/token" if settings.jira_server_url else None,
                "scopes": ["read:jira-user", "read:jira-work", "write:jira-work"]
            },
            "slack": {
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "auth_url": "https://slack.com/oauth/v2/authorize",
                "token_url": "https://slack.com/api/oauth.v2.access",
                "scopes": ["app_mentions:read", "channels:read", "chat:write", "commands", "users:read"]
            },
            "github": {
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "auth_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "scopes": ["repo", "user:email", "read:org"]
            }
        }
        self._state_cache = {}  # In production, use Redis or database
    
    def _generate_state(self, user_id: int, service: str) -> str:
        """Generate secure state parameter for OAuth flow."""
        state_data = {
            "user_id": user_id,
            "service": service,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_urlsafe(16)
        }
        
        state_string = json.dumps(state_data)
        state_token = base64.urlsafe_b64encode(state_string.encode()).decode()
        
        # Cache the state for validation
        self._state_cache[state_token] = state_data
        
        return state_token
    
    def _validate_state(self, state: str, user_id: int, service: str) -> bool:
        """Validate OAuth state parameter."""
        try:
            if state not in self._state_cache:
                return False
            
            state_data = self._state_cache[state]
            
            # Check if state matches expected user and service
            if (state_data["user_id"] != user_id or 
                state_data["service"] != service):
                return False
            
            # Check if state is not expired (10 minutes)
            timestamp = datetime.fromisoformat(state_data["timestamp"])
            if datetime.now(timezone.utc) - timestamp > timedelta(minutes=10):
                return False
            
            # Remove used state
            del self._state_cache[state]
            return True
            
        except (json.JSONDecodeError, KeyError, ValueError):
            return False
    
    def get_jira_auth_url(self, user_id: int) -> str:
        """Generate Jira OAuth authorization URL."""
        config = self.client_configs["jira"]
        
        if not config["client_id"] or not config["auth_url"]:
            raise IntegrationError("Jira OAuth not configured", "jira")
        
        state = self._generate_state(user_id, "jira")
        
        params = {
            "response_type": "code",
            "client_id": config["client_id"],
            "scope": " ".join(config["scopes"]),
            "state": state,
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/jira/callback"
        }
        
        return f"{config['auth_url']}?{urlencode(params)}"
    
    def get_slack_auth_url(self, user_id: int) -> str:
        """Generate Slack OAuth authorization URL."""
        config = self.client_configs["slack"]
        
        if not config["client_id"]:
            raise IntegrationError("Slack OAuth not configured", "slack")
        
        state = self._generate_state(user_id, "slack")
        
        params = {
            "response_type": "code",
            "client_id": config["client_id"],
            "scope": ",".join(config["scopes"]),
            "state": state,
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/slack/callback"
        }
        
        return f"{config['auth_url']}?{urlencode(params)}"
    
    def get_github_auth_url(self, user_id: int) -> str:
        """Generate GitHub OAuth authorization URL."""
        config = self.client_configs["github"]
        
        if not config["client_id"]:
            raise IntegrationError("GitHub OAuth not configured", "github")
        
        state = self._generate_state(user_id, "github")
        
        params = {
            "response_type": "code",
            "client_id": config["client_id"],
            "scope": " ".join(config["scopes"]),
            "state": state,
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/github/callback"
        }
        
        return f"{config['auth_url']}?{urlencode(params)}"
    
    async def handle_jira_callback(self, code: str, state: str, user_id: int) -> Dict[str, Any]:
        """Handle Jira OAuth callback and exchange code for token."""
        if not self._validate_state(state, user_id, "jira"):
            raise AuthenticationError("Invalid OAuth state", "jira")
        
        config = self.client_configs["jira"]
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/jira/callback"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=token_data,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                raise AuthenticationError(
                    f"Token exchange failed: {response.status_code}",
                    "jira",
                    response.status_code
                )
            
            token_response = response.json()
            
            # Add expiration time
            if "expires_in" in token_response:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_response["expires_in"])
                token_response["expires_at"] = expires_at.isoformat()
            
            return token_response
    
    async def handle_slack_callback(self, code: str, state: str, user_id: int) -> Dict[str, Any]:
        """Handle Slack OAuth callback and exchange code for token."""
        if not self._validate_state(state, user_id, "slack"):
            raise AuthenticationError("Invalid OAuth state", "slack")
        
        config = self.client_configs["slack"]
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/slack/callback"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=token_data,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                raise AuthenticationError(
                    f"Token exchange failed: {response.status_code}",
                    "slack",
                    response.status_code
                )
            
            token_response = response.json()
            
            if not token_response.get("ok"):
                raise AuthenticationError(
                    f"Slack OAuth error: {token_response.get('error', 'Unknown error')}",
                    "slack"
                )
            
            return token_response
    
    async def handle_github_callback(self, code: str, state: str, user_id: int) -> Dict[str, Any]:
        """Handle GitHub OAuth callback and exchange code for token."""
        if not self._validate_state(state, user_id, "github"):
            raise AuthenticationError("Invalid OAuth state", "github")
        
        config = self.client_configs["github"]
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": f"{settings.app_url}/api/v1/integrations/github/callback"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=token_data,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AI-Scrum-Master"
                }
            )
            
            if response.status_code != 200:
                raise AuthenticationError(
                    f"Token exchange failed: {response.status_code}",
                    "github",
                    response.status_code
                )
            
            token_response = response.json()
            
            if "error" in token_response:
                raise AuthenticationError(
                    f"GitHub OAuth error: {token_response['error_description']}",
                    "github"
                )
            
            return token_response
    
    async def store_user_token(
        self,
        db: AsyncSession,
        user_id: int,
        service: str,
        token_data: Dict[str, Any]
    ) -> None:
        """Store OAuth token securely for user."""
        # In production, encrypt tokens before storage
        encrypted_token = self._encrypt_token(token_data)
        
        # Update user model with encrypted token
        token_field_map = {
            "jira": "jira_token",
            "slack": "slack_token", 
            "github": "github_token"
        }
        
        if service not in token_field_map:
            raise ValueError(f"Unsupported service: {service}")
        
        field_name = token_field_map[service]
        
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**{field_name: encrypted_token})
        )
        
        await db.execute(stmt)
        await db.commit()
    
    async def get_user_token(
        self,
        db: AsyncSession,
        user_id: int,
        service: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt user token for service."""
        token_field_map = {
            "jira": "jira_token",
            "slack": "slack_token",
            "github": "github_token"
        }
        
        if service not in token_field_map:
            raise ValueError(f"Unsupported service: {service}")
        
        field_name = token_field_map[service]
        
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        encrypted_token = getattr(user, field_name)
        if not encrypted_token:
            return None
        
        return self._decrypt_token(encrypted_token)
    
    async def revoke_user_token(
        self,
        db: AsyncSession,
        user_id: int,
        service: str
    ) -> None:
        """Revoke and remove user token for service."""
        token_field_map = {
            "jira": "jira_token",
            "slack": "slack_token",
            "github": "github_token"
        }
        
        if service not in token_field_map:
            raise ValueError(f"Unsupported service: {service}")
        
        field_name = token_field_map[service]
        
        # TODO: Call service's token revocation endpoint if available
        
        # Clear token from database
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**{field_name: None})
        )
        
        await db.execute(stmt)
        await db.commit()
    
    async def refresh_token(
        self,
        db: AsyncSession,
        user_id: int,
        service: str
    ) -> Optional[Dict[str, Any]]:
        """Refresh expired OAuth token."""
        token_data = await self.get_user_token(db, user_id, service)
        
        if not token_data or "refresh_token" not in token_data:
            return None
        
        config = self.client_configs[service]
        
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=refresh_data,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                # Refresh failed, token is invalid
                await self.revoke_user_token(db, user_id, service)
                return None
            
            new_token_data = response.json()
            
            # Add expiration time
            if "expires_in" in new_token_data:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_token_data["expires_in"])
                new_token_data["expires_at"] = expires_at.isoformat()
            
            # Store new token
            await self.store_user_token(db, user_id, service, new_token_data)
            
            return new_token_data
    
    def _encrypt_token(self, token_data: Dict[str, Any]) -> str:
        """Encrypt token data for storage."""
        # Simple base64 encoding for now
        # In production, use proper encryption with Fernet or similar
        token_json = json.dumps(token_data)
        encrypted = base64.b64encode(token_json.encode()).decode()
        return encrypted
    
    def _decrypt_token(self, encrypted_token: str) -> Dict[str, Any]:
        """Decrypt token data from storage."""
        # Simple base64 decoding for now
        # In production, use proper decryption
        try:
            token_json = base64.b64decode(encrypted_token.encode()).decode()
            return json.loads(token_json)
        except (ValueError, json.JSONDecodeError):
            return {}