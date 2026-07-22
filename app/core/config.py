"""
Flourish Governed Memory Hub - Core Configuration Settings
Loads environment variables using Pydantic v2 BaseSettings.
Supports both Local Docker (`docker-compose.yml`) and Supabase Cloud PostgreSQL.
"""

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment & Project Metadata
    PROJECT_NAME: str = Field(
        "Flourish Governed Memory Hub Prototype", description="Application Title"
    )
    VERSION: str = Field("0.1.0", description="Application Version")
    ENVIRONMENT: str = Field(
        "development", description="Execution Environment: development, staging, production"
    )

    # Database Configuration (PostgreSQL 16 + pgvector via psycopg3)
    DATABASE_URL: str = Field(
        "postgresql+psycopg://postgres:postgres@localhost:5432/flourish_memory_hub",
        description="Async connection string to PostgreSQL / Supabase instance",
    )
    DB_POOL_SIZE: int = Field(20, description="SQLAlchemy connection pool base size")
    DB_MAX_OVERFLOW: int = Field(10, description="SQLAlchemy connection pool overflow allowance")
    DB_POOL_TIMEOUT: int = Field(30, description="Connection pool acquisition timeout in seconds")
    DB_ECHO: bool = Field(
        False, description="Whether to echo generated SQL statements to standard output"
    )

    # Cryptographic Audit Hash Chainer Secret Key (HMAC SHA-256)
    AUDIT_HMAC_SECRET: str = Field(
        ...,
        description="256-bit runtime environment secret key for audit log HMAC chaining",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """Ensures the database connection URL uses the async psycopg driver."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


# We suppress [call-arg] below because MyPy doesn't recognize Pydantic BaseSettings injecting defaults/env vars automatically.
settings = Settings()  # type: ignore[call-arg]
