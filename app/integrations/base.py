from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, TypeVar, Generic
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

# Type variables
T = TypeVar('T')
ConfigType = TypeVar('ConfigType', bound='IntegrationConfig')

# Enums
class IntegrationStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    EXPIRED = "expired"

class IntegrationScope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

# Base configuration
class IntegrationConfig(BaseModel):
    """Base configuration for all integrations."""
    
    name: str
    enabled: bool = True
    timeout: int = Field(default=30, ge=1, le=300)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    rate_limit_per_minute: int = Field(default=60, ge=1)
    
    class Config:
        extra = "forbid"

# Data models
class IntegrationCredentials(BaseModel):
    """Secure credential storage."""
    
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: List[str] = Field(default_factory=list)
    
    @property
    def is_expired(self) -> bool:
        """Check if credentials are expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at
    
    @property
    def expires_in_seconds(self) -> Optional[int]:
        """Get seconds until expiration."""
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))

class RateLimitInfo(BaseModel):
    """Rate limit tracking information."""
    
    limit: int
    remaining: int
    reset_at: datetime
    
    @property
    def is_exceeded(self) -> bool:
        """Check if rate limit is exceeded."""
        return self.remaining <= 0 and datetime.now(timezone.utc) < self.reset_at

class IntegrationMetrics(BaseModel):
    """Integration performance metrics."""
    
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    last_error: Optional[str] = None
    last_success: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

# Custom exceptions
class IntegrationError(Exception):
    """Base exception for integration errors."""
    
    def __init__(
        self, 
        message: str, 
        integration_name: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.integration_name = integration_name
        self.status_code = status_code
        self.response_data = response_data
        self.timestamp = datetime.now(timezone.utc)

class AuthenticationError(IntegrationError):
    """Authentication failed."""
    pass

class AuthorizationError(IntegrationError):
    """Authorization/permission denied."""
    pass

class RateLimitError(IntegrationError):
    """Rate limit exceeded."""
    
    def __init__(
        self, 
        message: str, 
        integration_name: str,
        reset_at: datetime,
        **kwargs
    ) -> None:
        super().__init__(message, integration_name, **kwargs)
        self.reset_at = reset_at

class ValidationError(IntegrationError):
    """Data validation failed."""
    pass

class NetworkError(IntegrationError):
    """Network/connectivity error."""
    pass

# Base integration class
class BaseIntegration(ABC, Generic[ConfigType]):
    """
    Abstract base class for all external service integrations.
    
    Provides common functionality:
    - HTTP client management
    - Rate limiting
    - Retry logic
    - Error handling
    - Metrics tracking
    - Credential management
    """
    
    def __init__(
        self,
        config: ConfigType,
        credentials: Optional[IntegrationCredentials] = None,
        db: Optional[AsyncSession] = None
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.db = db
        self.status = IntegrationStatus.DISCONNECTED
        self.metrics = IntegrationMetrics()
        self.rate_limit: Optional[RateLimitInfo] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @property
    def is_connected(self) -> bool:
        """Check if integration is properly connected."""
        return (
            self.status == IntegrationStatus.CONNECTED and
            self.credentials is not None and
            not self.credentials.is_expired
        )
    
    @property
    def can_make_request(self) -> bool:
        """Check if we can make API requests."""
        return (
            self.is_connected and
            (self.rate_limit is None or not self.rate_limit.is_exceeded)
        )
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the service."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the service."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if connection is working."""
        pass
    
    @abstractmethod
    async def refresh_credentials(self) -> None:
        """Refresh expired credentials."""
        pass
    
    async def __aenter__(self) -> BaseIntegration[ConfigType]:
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
    
    @asynccontextmanager
    async def _get_client(self):
        """Get HTTP client with proper lifecycle management."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.timeout,
                headers=self._get_default_headers()
            )
        
        try:
            yield self._client
        finally:
            # Keep client alive for reuse, close on disconnect
            pass
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "User-Agent": f"AI-Scrum-Master/{self.config.name}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if self.credentials and self.credentials.access_token:
            headers["Authorization"] = f"Bearer {self.credentials.access_token}"
        
        return headers
    
    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with error handling and retry logic.
        
        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request parameters
            
        Returns:
            HTTP response
            
        Raises:
            Various IntegrationError subclasses
        """
        if not self.can_make_request:
            if self.credentials and self.credentials.is_expired:
                await self.refresh_credentials()
            elif self.rate_limit and self.rate_limit.is_exceeded:
                raise RateLimitError(
                    f"Rate limit exceeded for {self.config.name}",
                    self.config.name,
                    self.rate_limit.reset_at
                )
        
        start_time = datetime.now(timezone.utc)
        
        for attempt in range(self.config.retry_attempts + 1):
            try:
                async with self._get_client() as client:
                    response = await client.request(method, url, **kwargs)
                    
                    # Update rate limit info
                    self._update_rate_limit_from_response(response)
                    
                    # Handle response
                    if response.is_success:
                        self._update_metrics_success(start_time)
                        return response
                    elif response.status_code == 401:
                        raise AuthenticationError(
                            "Authentication failed",
                            self.config.name,
                            response.status_code,
                            self._safe_json(response)
                        )
                    elif response.status_code == 403:
                        raise AuthorizationError(
                            "Authorization denied",
                            self.config.name,
                            response.status_code,
                            self._safe_json(response)
                        )
                    elif response.status_code == 429:
                        retry_after = self._get_retry_after(response)
                        raise RateLimitError(
                            "Rate limit exceeded",
                            self.config.name,
                            datetime.now(timezone.utc) + timedelta(seconds=retry_after),
                            status_code=response.status_code
                        )
                    elif 400 <= response.status_code < 500:
                        raise ValidationError(
                            f"Client error: {response.status_code}",
                            self.config.name,
                            response.status_code,
                            self._safe_json(response)
                        )
                    else:
                        # Server error - retry
                        if attempt < self.config.retry_attempts:
                            await asyncio.sleep(
                                self.config.retry_delay * (2 ** attempt)
                            )
                            continue
                        
                        raise IntegrationError(
                            f"Server error: {response.status_code}",
                            self.config.name,
                            response.status_code,
                            self._safe_json(response)
                        )
            
            except httpx.TimeoutException as e:
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                
                raise NetworkError(
                    f"Request timeout after {self.config.timeout}s",
                    self.config.name
                ) from e
            
            except httpx.NetworkError as e:
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                
                raise NetworkError(
                    f"Network error: {str(e)}",
                    self.config.name
                ) from e
        
        # Should never reach here
        raise IntegrationError(
            "Request failed after all retries",
            self.config.name
        )
    
    def _update_rate_limit_from_response(self, response: httpx.Response) -> None:
        """Update rate limit info from response headers."""
        headers = response.headers
        
        # Common rate limit headers
        if "x-ratelimit-remaining" in headers:
            try:
                self.rate_limit = RateLimitInfo(
                    limit=int(headers.get("x-ratelimit-limit", "60")),
                    remaining=int(headers["x-ratelimit-remaining"]),
                    reset_at=datetime.fromtimestamp(
                        int(headers.get("x-ratelimit-reset", "0"))
                    )
                )
            except (ValueError, KeyError):
                pass
    
    def _get_retry_after(self, response: httpx.Response) -> int:
        """Get retry-after seconds from response."""
        retry_after = response.headers.get("retry-after", "60")
        try:
            return int(retry_after)
        except ValueError:
            return 60
    
    def _safe_json(self, response: httpx.Response) -> Optional[Dict[str, Any]]:
        """Safely parse JSON response."""
        try:
            return response.json()
        except Exception:
            return None
    
    def _update_metrics_success(self, start_time: datetime) -> None:
        """Update metrics for successful request."""
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        self.metrics.total_requests += 1
        self.metrics.successful_requests += 1
        self.metrics.last_success = datetime.now(timezone.utc)
        
        # Update rolling average
        if self.metrics.average_response_time == 0:
            self.metrics.average_response_time = duration
        else:
            self.metrics.average_response_time = (
                (self.metrics.average_response_time * 0.9) + (duration * 0.1)
            )
    
    def _update_metrics_failure(self, error: str) -> None:
        """Update metrics for failed request."""
        self.metrics.total_requests += 1
        self.metrics.failed_requests += 1
        self.metrics.last_error = error
    
    async def get_metrics(self) -> IntegrationMetrics:
        """Get current integration metrics."""
        return self.metrics.model_copy()
    
    async def reset_metrics(self) -> None:
        """Reset integration metrics."""
        self.metrics = IntegrationMetrics()
    
    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
        
        self.status = IntegrationStatus.DISCONNECTED


# Utility functions
def create_integration_logger(integration_name: str) -> logging.Logger:
    """Create a logger for an integration."""
    logger = logging.getLogger(f"integrations.{integration_name}")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            f"%(asctime)s - {integration_name} - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def validate_url(url: str) -> bool:
    """Validate URL format."""
    try:
        from urllib.parse import urlparse
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def mask_sensitive_data(data: Dict[str, Any], sensitive_keys: List[str]) -> Dict[str, Any]:
    """Mask sensitive data in dictionary for logging."""
    masked = data.copy()
    
    for key in sensitive_keys:
        if key in masked:
            if isinstance(masked[key], str) and len(masked[key]) > 4:
                masked[key] = masked[key][:4] + "***"
            else:
                masked[key] = "***"
    
    return masked


# Export types and utilities
__all__ = [
    "BaseIntegration",
    "IntegrationConfig", 
    "IntegrationCredentials",
    "IntegrationStatus",
    "IntegrationScope",
    "RateLimitInfo",
    "IntegrationMetrics",
    "IntegrationError",
    "AuthenticationError",
    "AuthorizationError", 
    "RateLimitError",
    "ValidationError",
    "NetworkError",
    "create_integration_logger",
    "validate_url",
    "mask_sensitive_data"
]
