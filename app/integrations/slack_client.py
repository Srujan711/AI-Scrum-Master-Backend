from __future__ import annotations

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta, date, timezone
import json
import hashlib
import hmac

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from .base import (
    BaseIntegration,
    IntegrationConfig,
    IntegrationCredentials,
    IntegrationStatus,
    AuthenticationError,
    ValidationError,
    IntegrationError
)

# Slack-specific models
class SlackConfig(IntegrationConfig):
    """Slack integration configuration."""
    
    name: str = "slack"
    bot_token: Optional[str] = None
    app_token: Optional[str] = None
    signing_secret: Optional[str] = None
    default_channel: Optional[str] = None

class SlackMessage(BaseModel):
    """Slack message representation."""
    
    ts: str
    channel: str
    user: str
    text: str
    thread_ts: Optional[str] = None
    reactions: List[Dict[str, Any]] = Field(default_factory=list)
    files: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime
    
    @classmethod
    def from_slack_data(cls, data: Dict[str, Any]) -> 'SlackMessage':
        """Create from Slack API response."""
        return cls(
            ts=data["ts"],
            channel=data.get("channel", ""),
            user=data.get("user", ""),
            text=data.get("text", ""),
            thread_ts=data.get("thread_ts"),
            reactions=data.get("reactions", []),
            files=data.get("files", []),
            timestamp=datetime.fromtimestamp(float(data["ts"]))
        )

class SlackChannel(BaseModel):
    """Slack channel representation."""
    
    id: str
    name: str
    is_channel: bool
    is_group: bool
    is_im: bool
    is_member: bool
    is_private: bool
    topic: str = ""
    purpose: str = ""
    num_members: int = 0

class SlackUser(BaseModel):
    """Slack user representation."""
    
    id: str
    name: str
    real_name: str
    display_name: str = ""
    email: Optional[str] = None
    is_bot: bool = False
    is_admin: bool = False
    timezone: Optional[str] = None

class SlackError(IntegrationError):
    """Slack-specific error."""
    pass

# Main Slack client
class SlackClient(BaseIntegration[SlackConfig]):
    """
    Production-ready Slack integration client.
    
    Features:
    - Message posting and retrieval
    - Channel management
    - User interactions
    - File uploads
    - Interactive components
    - Webhook verification
    """
    
    def __init__(
        self,
        config: SlackConfig,
        credentials: Optional[IntegrationCredentials] = None,
        db: Optional[AsyncSession] = None
    ) -> None:
        super().__init__(config, credentials, db)
        self._client: Optional[AsyncWebClient] = None
    
    async def connect(self) -> None:
        """Connect to Slack."""
        self._logger.info("Connecting to Slack")
        
        try:
            token = None
            if self.credentials and self.credentials.access_token:
                token = self.credentials.access_token
            elif self.config.bot_token:
                token = self.config.bot_token
            
            if not token:
                raise AuthenticationError(
                    "No valid token provided",
                    self.config.name
                )
            
            self._client = AsyncWebClient(token=token)
            
            # Test connection
            await self.test_connection()
            self.status = IntegrationStatus.CONNECTED
            self._logger.info("Successfully connected to Slack")
            
        except Exception as e:
            self.status = IntegrationStatus.ERROR
            self._logger.error("Failed to connect to Slack: %s", str(e))
            raise SlackError(
                f"Connection failed: {str(e)}",
                self.config.name
            ) from e
    
    async def disconnect(self) -> None:
        """Disconnect from Slack."""
        if self._client:
            # Slack SDK doesn't require explicit cleanup
            self._client = None
        
        self.status = IntegrationStatus.DISCONNECTED
        await self.close()
        self._logger.info("Disconnected from Slack")
    
    async def test_connection(self) -> bool:
        """Test Slack connection."""
        if not self._client:
            return False
        
        try:
            response = await self._client.auth_test()
            if response["ok"]:
                self._logger.debug("Connection test successful, bot: %s", response.get("user"))
                return True
            else:
                self._logger.error("Auth test failed: %s", response.get("error"))
                return False
        except Exception as e:
            self._logger.error("Connection test failed: %s", str(e))
            return False
    
    async def refresh_credentials(self) -> None:
        """Refresh credentials (Slack tokens don't typically expire)."""
        self._logger.info("Slack tokens typically don't require refresh")
        await self.connect()
    
    # Message operations
    
    async def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> SlackMessage:
        """Post message to channel."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            response = await self._client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                blocks=blocks,
                attachments=attachments
            )
            
            if response["ok"]:
                return SlackMessage.from_slack_data(response["message"])
            else:
                raise SlackError(
                    f"Failed to post message: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> SlackMessage:
        """Update existing message."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            response = await self._client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks
            )
            
            if response["ok"]:
                return SlackMessage.from_slack_data(response["message"])
            else:
                raise SlackError(
                    f"Failed to update message: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    async def get_channel_messages(
        self,
        channel: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SlackMessage]:
        """Get messages from channel."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            kwargs = {
                "channel": channel,
                "limit": limit
            }
            
            if since:
                kwargs["oldest"] = str(since.timestamp())
            
            response = await self._client.conversations_history(**kwargs)
            
            if response["ok"]:
                messages = []
                for msg_data in response.get("messages", []):
                    messages.append(SlackMessage.from_slack_data(msg_data))
                return messages
            else:
                raise SlackError(
                    f"Failed to get messages: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    # Channel operations
    
    async def get_channel_info(self, channel: str) -> SlackChannel:
        """Get channel information."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            response = await self._client.conversations_info(channel=channel)
            
            if response["ok"]:
                channel_data = response["channel"]
                return SlackChannel(
                    id=channel_data["id"],
                    name=channel_data.get("name", ""),
                    is_channel=channel_data.get("is_channel", False),
                    is_group=channel_data.get("is_group", False),
                    is_im=channel_data.get("is_im", False),
                    is_member=channel_data.get("is_member", False),
                    is_private=channel_data.get("is_private", False),
                    topic=channel_data.get("topic", {}).get("value", ""),
                    purpose=channel_data.get("purpose", {}).get("value", ""),
                    num_members=channel_data.get("num_members", 0)
                )
            else:
                raise SlackError(
                    f"Failed to get channel info: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    async def list_channels(self, exclude_archived: bool = True) -> List[SlackChannel]:
        """List all channels."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            response = await self._client.conversations_list(
                exclude_archived=exclude_archived,
                types="public_channel,private_channel"
            )
            
            if response["ok"]:
                channels = []
                for channel_data in response.get("channels", []):
                    channels.append(SlackChannel(
                        id=channel_data["id"],
                        name=channel_data.get("name", ""),
                        is_channel=channel_data.get("is_channel", False),
                        is_group=channel_data.get("is_group", False),
                        is_im=channel_data.get("is_im", False),
                        is_member=channel_data.get("is_member", False),
                        is_private=channel_data.get("is_private", False),
                        topic=channel_data.get("topic", {}).get("value", ""),
                        purpose=channel_data.get("purpose", {}).get("value", ""),
                        num_members=channel_data.get("num_members", 0)
                    ))
                return channels
            else:
                raise SlackError(
                    f"Failed to list channels: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    # User operations
    
    async def get_user_info(self, user_id: str) -> SlackUser:
        """Get user information."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        try:
            response = await self._client.users_info(user=user_id)
            
            if response["ok"]:
                user_data = response["user"]
                return SlackUser(
                    id=user_data["id"],
                    name=user_data.get("name", ""),
                    real_name=user_data.get("real_name", ""),
                    display_name=user_data.get("profile", {}).get("display_name", ""),
                    email=user_data.get("profile", {}).get("email"),
                    is_bot=user_data.get("is_bot", False),
                    is_admin=user_data.get("is_admin", False),
                    timezone=user_data.get("tz")
                )
            else:
                raise SlackError(
                    f"Failed to get user info: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    # AI Scrum Master specific methods
    
    async def post_standup_summary(
        self,
        channel: str,
        summary: str,
        action_items: List[Dict[str, Any]] = None
    ) -> SlackMessage:
        """Post standup summary with formatted blocks."""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Daily Standup Summary"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary
                }
            }
        ]
        
        if action_items:
            blocks.append({
                "type": "divider"
            })
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Action Items:*"
                }
            })
            
            for item in action_items:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {item.get('description', '')}"
                    }
                })
        
        return await self.post_message(channel, summary, blocks=blocks)
    
    async def get_standup_messages(
        self,
        channel: str,
        date: date,
        keywords: List[str] = None
    ) -> List[SlackMessage]:
        """Get standup-related messages from a specific date."""
        
        # Get messages from the specified date
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        messages = await self.get_channel_messages(
            channel=channel,
            since=start_of_day
        )
        
        # Filter messages from the specific date
        filtered_messages = [
            msg for msg in messages
            if start_of_day <= msg.timestamp < end_of_day
        ]
        
        # If keywords provided, filter by content
        if keywords:
            standup_keywords = keywords or ['standup', 'yesterday', 'today', 'blocker', 'done', 'working on']
            keyword_messages = []
            
            for msg in filtered_messages:
                if any(keyword.lower() in msg.text.lower() for keyword in standup_keywords):
                    keyword_messages.append(msg)
            
            return keyword_messages
        
        return filtered_messages
    
    async def create_sprint_channel(
        self,
        sprint_name: str,
        team_members: List[str],
        is_private: bool = False
    ) -> SlackChannel:
        """Create a channel for sprint communications."""
        if not self._client:
            raise SlackError("Not connected to Slack", self.config.name)
        
        # Create channel name from sprint name
        channel_name = sprint_name.lower().replace(" ", "-").replace("_", "-")
        
        try:
            response = await self._client.conversations_create(
                name=channel_name,
                is_private=is_private
            )
            
            if response["ok"]:
                channel_id = response["channel"]["id"]
                
                # Invite team members
                for member in team_members:
                    try:
                        await self._client.conversations_invite(
                            channel=channel_id,
                            users=member
                        )
                    except SlackApiError:
                        # Continue if user can't be invited
                        pass
                
                # Set channel topic
                await self._client.conversations_setTopic(
                    channel=channel_id,
                    topic=f"Sprint: {sprint_name}"
                )
                
                return await self.get_channel_info(channel_id)
            else:
                raise SlackError(
                    f"Failed to create channel: {response.get('error')}",
                    self.config.name
                )
                
        except SlackApiError as e:
            raise SlackError(
                f"Slack API error: {str(e)}",
                self.config.name
            ) from e
    
    # Webhook verification
    
    def verify_webhook_signature(
        self,
        request_body: bytes,
        request_timestamp: str,
        request_signature: str
    ) -> bool:
        """Verify Slack webhook signature."""
        if not self.config.signing_secret:
            return False
        
        # Check timestamp (prevent replay attacks)
        timestamp = int(request_timestamp)
        current_time = int(datetime.now(timezone.utc).timestamp())
        
        if abs(current_time - timestamp) > 300:  # 5 minutes
            return False
        
        # Verify signature
        sig_basestring = f"v0:{request_timestamp}:{request_body.decode('utf-8')}"
        computed_signature = 'v0=' + hmac.new(
            self.config.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, request_signature)
    
    async def handle_event(self, event_data: Dict[str, Any]) -> None:
        """Handle incoming Slack events."""
        event_type = event_data.get("type")
        
        if event_type == "message":
            await self._handle_message_event(event_data)
        elif event_type == "app_mention":
            await self._handle_mention_event(event_data)
        # Add more event handlers as needed
    
    async def _handle_message_event(self, event_data: Dict[str, Any]) -> None:
        """Handle message events."""
        # Process message for standup keywords, AI triggers, etc.
        self._logger.info("Processing message event: %s", event_data.get("text", "")[:100])
    
    async def _handle_mention_event(self, event_data: Dict[str, Any]) -> None:
        """Handle app mention events."""
        # Respond to bot mentions
        channel = event_data.get("channel")
        user = event_data.get("user")
        
        if channel and user:
            await self.post_message(
                channel=channel,
                text=f"Hi <@{user}>! I'm your AI Scrum Master. How can I help you today?"
            )