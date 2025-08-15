from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from ...database import get_db
from ...core.auth import get_current_user
from ...models.user import User
from ...integrations.oauth_handlers import OAuthHandlers
from ...integrations.jira_client import JiraClient
from ...integrations.slack_client import SlackClient
from ...integrations.github_client import GitHubClient

router = APIRouter()

class OAuthCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None

class IntegrationStatus(BaseModel):
    service: str
    connected: bool
    last_sync: Optional[str]
    error_message: Optional[str]


@router.get("/status", response_model=List[IntegrationStatus])
async def get_integration_status(
    current_user: User = Depends(get_current_user)
):
    """Get status of all integrations for current user"""
    
    integrations = []
    
    # Check Jira
    integrations.append({
        "service": "jira",
        "connected": bool(current_user.jira_token),
        "last_sync": None,  # Would come from integration logs
        "error_message": None
    })
    
    # Check Slack
    integrations.append({
        "service": "slack",
        "connected": bool(current_user.slack_token),
        "last_sync": None,
        "error_message": None
    })
    
    # Check GitHub
    integrations.append({
        "service": "github",
        "connected": bool(current_user.github_token),
        "last_sync": None,
        "error_message": None
    })
    
    return integrations


@router.get("/jira/auth-url")
async def get_jira_auth_url(
    current_user: User = Depends(get_current_user)
):
    """Get Jira OAuth authorization URL"""
    
    oauth_handler = OAuthHandlers()
    auth_url = oauth_handler.get_jira_auth_url(user_id=current_user.id)
    
    return {"auth_url": auth_url}


@router.post("/jira/callback")
async def jira_oauth_callback(
    callback_data: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Handle Jira OAuth callback"""
    
    oauth_handler = OAuthHandlers()
    
    try:
        # Exchange code for token
        token_data = await oauth_handler.handle_jira_callback(
            code=callback_data.code,
            state=callback_data.state,
            user_id=current_user.id
        )
        
        # Store token securely (encrypted)
        await oauth_handler.store_user_token(
            db=db,
            user_id=current_user.id,
            service="jira",
            token_data=token_data
        )
        
        return {"message": "Jira integration connected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")


@router.get("/slack/auth-url")
async def get_slack_auth_url(
    current_user: User = Depends(get_current_user)
):
    """Get Slack OAuth authorization URL"""
    
    oauth_handler = OAuthHandlers()
    auth_url = oauth_handler.get_slack_auth_url(user_id=current_user.id)
    
    return {"auth_url": auth_url}


@router.post("/slack/callback")
async def slack_oauth_callback(
    callback_data: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Handle Slack OAuth callback"""
    
    oauth_handler = OAuthHandlers()
    
    try:
        token_data = await oauth_handler.handle_slack_callback(
            code=callback_data.code,
            state=callback_data.state,
            user_id=current_user.id
        )
        
        await oauth_handler.store_user_token(
            db=db,
            user_id=current_user.id,
            service="slack",
            token_data=token_data
        )
        
        return {"message": "Slack integration connected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")


@router.post("/slack/webhook")
async def slack_webhook_handler(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle incoming Slack webhooks/events"""
    
    # Verify Slack signature
    slack_client = SlackClient()
    
    body = await request.body()
    headers = request.headers
    
    if not slack_client.verify_signature(body, headers):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse webhook data
    webhook_data = await request.json()
    
    # Handle different event types
    event_type = webhook_data.get("type")
    
    if event_type == "url_verification":
        # Slack URL verification
        return {"challenge": webhook_data.get("challenge")}
    
    elif event_type == "event_callback":
        # Handle actual events
        event = webhook_data.get("event", {})
        await slack_client.handle_event(event, db)
        
        return {"status": "ok"}
    
    return {"status": "ignored"}


@router.delete("/{service}/disconnect")
async def disconnect_integration(
    service: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Disconnect an integration"""
    
    valid_services = ["jira", "slack", "github"]
    if service not in valid_services:
        raise HTTPException(status_code=400, detail="Invalid service")
    
    oauth_handler = OAuthHandlers()
    
    try:
        await oauth_handler.revoke_user_token(
            db=db,
            user_id=current_user.id,
            service=service
        )
        
        return {"message": f"{service.title()} integration disconnected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {str(e)}")


@router.post("/sync/{service}")
async def sync_integration_data(
    service: str,
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger data sync for an integration"""
    
    valid_services = ["jira", "slack", "github"]
    if service not in valid_services:
        raise HTTPException(status_code=400, detail="Invalid service")
    
    # Check user has access to team
    # This would be implemented in a service layer
    
    try:
        if service == "jira":
            jira_client = JiraClient(user_id=current_user.id)
            await jira_client.sync_team_data(team_id=team_id)
        
        elif service == "slack":
            slack_client = SlackClient(user_id=current_user.id)
            await slack_client.sync_team_data(team_id=team_id)
        
        elif service == "github":
            github_client = GitHubClient(user_id=current_user.id)
            await github_client.sync_team_data(team_id=team_id)
        
        return {"message": f"{service.title()} data synced successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
