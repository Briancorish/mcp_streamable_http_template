import os
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Base class for SQLAlchemy models. All models will inherit from this.
Base = declarative_base()

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
        # Ensure the URL uses the 'asyncpg' driver for the async engine.
        # This now correctly handles both postgresql:// and postgres:// prefixes.
        if raw_url.startswith("postgresql://"):
            return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if raw_url.startswith("postgres://"):
            return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        # Ensure the URL uses the default 'psycopg2' driver for the sync engine.
        if raw_url.startswith("postgres://"):
            return raw_url.replace("postgres://", "postgresql://", 1)

    return raw_url

