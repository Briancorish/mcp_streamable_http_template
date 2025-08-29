import sqlalchemy
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.sql import func
from database import Base

class UserCredentials(Base):
    """Store Google OAuth credentials for users"""
    __tablename__ = "user_credentials"
    
    id = sqlalchemy.Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = sqlalchemy.Column(String, nullable=False, unique=True, index=True)
    client_id = sqlalchemy.Column(String, nullable=False)
    client_secret = sqlalchemy.Column(String, nullable=False)
    token = sqlalchemy.Column(Text)  # JSON string containing access token
    refresh_token = sqlalchemy.Column(String)
    created_at = sqlalchemy.Column(DateTime, default=func.now())
    updated_at = sqlalchemy.Column(DateTime, default=func.now(), onupdate=func.now())
