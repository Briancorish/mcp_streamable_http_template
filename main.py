import os
import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

# FastMCP 2.0 imports
from fastmcp import FastMCP
from contextlib import asynccontextmanager
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Database imports
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from database import get_database_url, Base
from models import UserCredentials

# Google Calendar imports
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Setup (Async) ---
# Create an async-specific engine and session maker. This is crucial.
async_database_url = get_database_url(is_async=True)
async_engine = create_async_engine(async_database_url, echo=False)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


# Lifespan manager for initial database table creation
@asynccontextmanager
async def lifespan(app):
    """Handles startup and shutdown events for the server."""
    logger.info("Server startup: Creating database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully.")
    yield
    logger.info("Server shutdown.")





# API key authentication middleware
class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Let health checks and root path pass through without auth
        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        expected_key = os.getenv("CALENDAR_MCP_SERVER_API_KEY")
        
        if not expected_key:
            logger.warning("CALENDAR_MCP_SERVER_API_KEY is not set. Allowing request without auth.")
        elif api_key != expected_key:
            return JSONResponse({"error": "Invalid API key"}, status_code=401)
        
        return await call_next(request)


# Initialize FastMCP 2.0 server with lifespan and middleware
mcp_server = FastMCP(
    "Calendar MCP Server",
    lifespan=lifespan,
    middleware=[
        Middleware(ApiKeyAuthMiddleware)
    ]
)






async def get_google_credentials(user_id: str = "default") -> Optional[Credentials]:
    """Get Google credentials from database"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user_id)
        )
        user_creds = result.scalar_one_or_none()
        
        if not user_creds:
            logger.error(f"No credentials found for user {user_id}")
            return None
        
        try:
            token_data = json.loads(user_creds.token) if user_creds.token else {}
            credentials = Credentials(
                token=token_data.get("access_token"),
                refresh_token=user_creds.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=user_creds.client_id,
                client_secret=user_creds.client_secret,
                scopes=["https://www.googleapis.com/auth/calendar"]
            )
            
            # Check if credentials need refresh
            if not credentials.valid and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    # Update tokens in database
                    await session.execute(
                        update(UserCredentials)
                        .where(UserCredentials.user_id == user_id)
                        .values(
                            token=json.dumps({"access_token": credentials.token}),
                            updated_at=datetime.utcnow()
                        )
                    )
                    await session.commit()
                    logger.info(f"Refreshed credentials for user {user_id}")
                except RefreshError as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    return None
            
            return credentials
        except Exception as e:
            logger.error(f"Error creating credentials: {e}")
            return None

# MCP Tools

@mcp_server.tool(
    name="list_calendars",
    description="Lists the calendars on the user's calendar list"
)
async def list_calendars(min_access_role: Optional[str] = None) -> str:
    """Lists the calendars on the user's calendar list.
    
    Args:
        min_access_role: Minimum access role ('reader', 'writer', 'owner').
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        params = {}
        if min_access_role:
            params['minAccessRole'] = min_access_role
        
        calendars_result = service.calendarList().list(**params).execute()
        calendars = calendars_result.get('items', [])
        
        return json.dumps({
            "calendars": [
                {
                    "id": cal.get("id"),
                    "summary": cal.get("summary"),
                    "description": cal.get("description"),
                    "accessRole": cal.get("accessRole"),
                    "primary": cal.get("primary", False)
                }
                for cal in calendars
            ]
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in list_calendars: {e}")
        raise RuntimeError(f"Failed to list calendars: {str(e)}") from e

@mcp_server.tool(
    name="find_events",
    description="Find events in a specified calendar"
)
async def find_events(
    calendar_id: str,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 50
) -> str:
    """Find events in a specified calendar.
    
    Args:
        calendar_id: Calendar identifier (e.g., 'primary', email address, or calendar ID).
        time_min: Start time (inclusive, ISO format).
        time_max: End time (exclusive, ISO format).
        query: Free text search query.
        max_results: Maximum number of events to return.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        params = {
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime'
        }
        
        if time_min:
            params['timeMin'] = time_min
        if time_max:
            params['timeMax'] = time_max
        if query:
            params['q'] = query
        
        events_result = service.events().list(calendarId=calendar_id, **params).execute()
        events = events_result.get('items', [])
        
        return json.dumps({
            "events": [
                {
                    "id": event.get("id"),
                    "summary": event.get("summary"),
                    "description": event.get("description"),
                    "start": event.get("start"),
                    "end": event.get("end"),
                    "location": event.get("location"),
                    "attendees": event.get("attendees", [])
                }
                for event in events
            ]
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in find_events: {e}")
        raise RuntimeError(f"Failed to find events: {str(e)}") from e

@mcp_server.tool(
    name="create_event",
    description="Creates a new event with detailed information"
)
async def create_event(
    calendar_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendee_emails: Optional[List[str]] = None
) -> str:
    """Creates a new event with detailed information.
    
    Args:
        calendar_id: Calendar identifier.
        summary: Title of the event.
        start_time: Start time in ISO format.
        end_time: End time in ISO format.
        description: Optional description for the event.
        location: Optional location for the event.
        attendee_emails: Optional list of attendee email addresses.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        event_data = {
            'summary': summary,
            'start': {'dateTime': start_time},
            'end': {'dateTime': end_time}
        }
        
        if description:
            event_data['description'] = description
        if location:
            event_data['location'] = location
        if attendee_emails:
            event_data['attendees'] = [{'email': email} for email in attendee_emails]
        
        event = service.events().insert(calendarId=calendar_id, body=event_data).execute()
        
        return json.dumps({
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "htmlLink": event.get("htmlLink")
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in create_event: {e}")
        raise RuntimeError(f"Failed to create event: {str(e)}") from e

@mcp_server.tool(
    name="quick_add_event",
    description="Creates an event based on a simple text string using Google's natural language parser"
)
async def quick_add_event(calendar_id: str, text: str) -> str:
    """Creates an event based on a simple text string.
    
    Args:
        calendar_id: Calendar identifier.
        text: The text description of the event.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        event = service.events().quickAdd(calendarId=calendar_id, text=text).execute()
        
        return json.dumps({
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "htmlLink": event.get("htmlLink")
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in quick_add_event: {e}")
        raise RuntimeError(f"Failed to quick add event: {str(e)}") from e

@mcp_server.tool(
    name="update_event",
    description="Updates an existing event"
)
async def update_event(
    calendar_id: str,
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Updates an existing event.
    
    Args:
        calendar_id: Calendar identifier.
        event_id: Event identifier.
        summary: New title for the event.
        start_time: New start time in ISO format.
        end_time: New end time in ISO format.
        description: New description for the event.
        location: New location for the event.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        # Get current event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Update fields
        if summary:
            event['summary'] = summary
        if start_time:
            event['start'] = {'dateTime': start_time}
        if end_time:
            event['end'] = {'dateTime': end_time}
        if description:
            event['description'] = description
        if location:
            event['location'] = location
        
        updated_event = service.events().update(
            calendarId=calendar_id, 
            eventId=event_id, 
            body=event
        ).execute()
        
        return json.dumps({
            "id": updated_event.get("id"),
            "summary": updated_event.get("summary"),
            "start": updated_event.get("start"),
            "end": updated_event.get("end"),
            "htmlLink": updated_event.get("htmlLink")
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in update_event: {e}")
        raise RuntimeError(f"Failed to update event: {str(e)}") from e

@mcp_server.tool(
    name="delete_event",
    description="Deletes an event"
)
async def delete_event(calendar_id: str, event_id: str) -> str:
    """Deletes an event.
    
    Args:
        calendar_id: Calendar identifier.
        event_id: Event identifier.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        
        return json.dumps({"success": "Event successfully deleted"})
    except Exception as e:
        logger.error(f"Error in delete_event: {e}")
        raise RuntimeError(f"Failed to delete event: {str(e)}") from e

@mcp_server.tool(
    name="query_free_busy",
    description="Queries the free/busy information for a list of calendars over a time period"
)
async def query_free_busy(calendar_ids: List[str], time_min: str, time_max: str) -> str:
    """Queries the free/busy information for calendars.
    
    Args:
        calendar_ids: List of calendar identifiers to query.
        time_min: Start of the time range (ISO format).
        time_max: End of the time range (ISO format).
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        body = {
            'timeMin': time_min,
            'timeMax': time_max,
            'items': [{'id': calendar_id} for calendar_id in calendar_ids]
        }
        
        freebusy = service.freebusy().query(body=body).execute()
        
        return json.dumps(freebusy, indent=2)
    except Exception as e:
        logger.error(f"Error in query_free_busy: {e}")
        raise RuntimeError(f"Failed to query free/busy information: {str(e)}") from e

@mcp_server.tool(
    name="create_calendar",
    description="Creates a new secondary calendar"
)
async def create_calendar(summary: str) -> str:
    """Creates a new secondary calendar.
    
    Args:
        summary: The title for the new calendar.
    """
    try:
        credentials = await get_google_credentials()
        if not credentials:
            raise RuntimeError("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=credentials)
        
        calendar_data = {'summary': summary}
        created_calendar = service.calendars().insert(body=calendar_data).execute()
        
        return json.dumps({
            "id": created_calendar.get("id"),
            "summary": created_calendar.get("summary"),
            "description": created_calendar.get("description")
        }, indent=2)
    except Exception as e:
        logger.error(f"Error in create_calendar: {e}")
        raise RuntimeError(f"Failed to create calendar: {str(e)}") from e

# Additional admin tool for credential management
@mcp_server.tool(
    name="setup_credentials",
    description="Setup Google OAuth credentials for the MCP server"
)
async def setup_credentials(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    user_id: str = "default"
) -> str:
    """Setup Google OAuth credentials.
    
    Args:
        client_id: Google OAuth client ID.
        client_secret: Google OAuth client secret.
        refresh_token: Google OAuth refresh token.
        user_id: User identifier (default: 'default').
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check if credentials already exist
            result = await session.execute(
                select(UserCredentials).where(UserCredentials.user_id == user_id)
            )
            existing_creds = result.scalar_one_or_none()
            
            if existing_creds:
                # Update existing credentials
                await session.execute(
                    update(UserCredentials)
                    .where(UserCredentials.user_id == user_id)
                    .values(
                        client_id=client_id,
                        client_secret=client_secret,
                        refresh_token=refresh_token,
                        updated_at=datetime.utcnow()
                    )
                )
            else:
                # Create new credentials
                new_creds = UserCredentials(
                    user_id=user_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh_token
                )
                session.add(new_creds)
            
            await session.commit()
            
            return json.dumps({
                "success": f"Credentials set up successfully for user {user_id}"
            })
    except Exception as e:
        logger.error(f"Error in setup_credentials: {e}")
        raise RuntimeError(f"Failed to setup credentials: {str(e)}") from e

    # Start the server
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    mcp_server.run(
        transport="streamable-http",
        host=host,
        port=port,
        path="/mcp",
        log_level="info"
    )
