from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    # Application
    app_name: str = "AI Scrum Master"
    app_version: str = "1.0.0"
    app_url: str = Field(default="http://localhost:8000", env="APP_URL")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Database
    database_url: str = Field(env="DATABASE_URL")
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")
    
    # Authentication & Security
    secret_key: str = Field(env="SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # AI & LLM Configuration
    llm_provider: str = Field(default="openai", env="LLM_PROVIDER")  # openai or ollama
    
    # OpenAI Configuration (legacy/optional)
    openai_api_key: str = Field(default="not-needed", env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4", env="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.3, env="OPENAI_TEMPERATURE")
    max_tokens: int = Field(default=2000, env="MAX_TOKENS")
    
    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.2", env="OLLAMA_MODEL")
    ollama_temperature: float = Field(default=0.3, env="OLLAMA_TEMPERATURE")
    
    # Vector Database
    vector_db_provider: str = Field(default="pinecone", env="VECTOR_DB_PROVIDER")  # pinecone, weaviate, chroma
    pinecone_api_key: Optional[str] = Field(default=None, env="PINECONE_API_KEY")
    pinecone_environment: Optional[str] = Field(default=None, env="PINECONE_ENVIRONMENT")
    pinecone_index_name: str = Field(default="ai-scrum-master", env="PINECONE_INDEX_NAME")
    
    # External Integrations
    # Jira
    jira_server_url: Optional[str] = Field(default=None, env="JIRA_SERVER_URL")
    jira_client_id: Optional[str] = Field(default=None, env="JIRA_CLIENT_ID")
    jira_client_secret: Optional[str] = Field(default=None, env="JIRA_CLIENT_SECRET")
    
    # Slack
    slack_client_id: Optional[str] = Field(default=None, env="SLACK_CLIENT_ID")
    slack_client_secret: Optional[str] = Field(default=None, env="SLACK_CLIENT_SECRET")
    slack_signing_secret: Optional[str] = Field(default=None, env="SLACK_SIGNING_SECRET")
    
    # GitHub
    github_client_id: Optional[str] = Field(default=None, env="GITHUB_CLIENT_ID")
    github_client_secret: Optional[str] = Field(default=None, env="GITHUB_CLIENT_SECRET")
    
    # Workflow & Scheduling
    enable_scheduled_tasks: bool = Field(default=True, env="ENABLE_SCHEDULED_TASKS")
    default_standup_time: str = Field(default="09:00", env="DEFAULT_STANDUP_TIME")
    timezone: str = Field(default="UTC", env="TIMEZONE")
    
    # Redis (for caching and task queue)
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"], 
        env="ALLOWED_ORIGINS"
    )
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # Feature Flags
    enable_ai_suggestions: bool = Field(default=True, env="ENABLE_AI_SUGGESTIONS")
    enable_auto_ticket_creation: bool = Field(default=False, env="ENABLE_AUTO_TICKET_CREATION")
    enable_analytics: bool = Field(default=True, env="ENABLE_ANALYTICS")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=3600, env="RATE_LIMIT_WINDOW")  # seconds
    
    # AI Agent Configuration
    max_agent_iterations: int = Field(default=10, env="MAX_AGENT_ITERATIONS")
    agent_timeout: int = Field(default=300, env="AGENT_TIMEOUT")  # seconds


# Global settings instance
settings = Settings()


# Environment-specific configurations
class DevelopmentConfig(Settings):
    debug: bool = True
    database_echo: bool = True
    log_level: str = "DEBUG"


class ProductionConfig(Settings):
    debug: bool = False
    database_echo: bool = False
    log_level: str = "WARNING"


class TestingConfig(Settings):
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "test-secret-key"
    openai_api_key: str = "test-openai-key"


def get_settings() -> Settings:
    """Factory function to get settings based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionConfig()
    elif env == "testing":
        return TestingConfig()
    else:
        return DevelopmentConfig()