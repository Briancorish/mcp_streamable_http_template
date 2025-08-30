import os
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Base class for SQLAlchemy models. All models will inherit from this.
Base = declarative_base()


def _ensure_sslmode(url: str) -> str:
    if not url:
        return url
    if 'sslmode=' in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}sslmode=require"


def get_database_url(is_async: bool = False) -> str:
    """
    Constructs the correct database URL from environment variables.
    Handles Render's default URL format and converts it for async if needed.
    """
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        # Fallback for local development if DATABASE_URL is not set
        return "postgresql+asyncpg://localhost/calendar_mcp" if is_async else "postgresql://localhost/calendar_mcp"

    if is_async:
        # For async engine, ensure we use the asyncpg driver
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif raw_url.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return _ensure_sslmode(raw_url)
    else:
        # For sync engine, normalize to psycopg2 driver prefix
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql://", 1)
        return _ensure_sslmode(raw_url)
