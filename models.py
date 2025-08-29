import sqlalchemy
from database import Base

class UserCredentials(Base):
    """Store Google OAuth credentials for users"""
    __tablename__ = "user_credentials"
    
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True, index=True)
    client_id = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    client_secret = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    token = sqlalchemy.Column(sqlalchemy.Text)  # JSON string containing access token
    refresh_token = sqlalchemy.Column(sqlalchemy.String)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime, default=sqlalchemy.func.now())
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime, default=sqlalchemy.func.now(), onupdate=sqlalchemy.func.now())
