"""
services/gcal.py — Google Calendar API integration
Uses OAuth2 (user-level) so events appear in the user's personal Google Calendar.

Flow:
  1. User clicks "Conectar Google Calendar" → /calendario/gcal/auth
  2. Google redirects back → /calendario/gcal/callback  (saves token in DB)
  3. Every CalendarEvent create/update/delete calls push_event / delete_event

Requires .env:
  GOOGLE_OAUTH_CLIENT_ID=...
  GOOGLE_OAUTH_CLIENT_SECRET=...
  GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5001/calendario/gcal/callback
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

log = logging.getLogger("gcal")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
GCAL_CALENDAR_ID = "primary"  # Use the user's primary calendar

def _get_client_id() -> str:
    """Read client ID from env at call time (not module import time)."""
    return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")


def _get_client_secret() -> str:
    """Read client secret from env at call time (not module import time)."""
    return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")


def _redirect_uri() -> str:
    """Return the redirect URI for the current request, or the env-var fallback."""
    try:
        from flask import request
        return request.host_url.rstrip("/") + "/calendario/gcal/callback"
    except Exception:
        return os.environ.get(
            "GOOGLE_OAUTH_REDIRECT_URI",
            "http://localhost:5001/calendario/gcal/callback",
        )


def _client_config(redirect_uri: str):
    # "installed" is the correct key for Desktop / Installed App OAuth clients.
    # Google Cloud Console → Credentials → type "Escritorio / Desktop".
    # These clients automatically allow http://localhost on any port.
    return {
        "installed": {
            "client_id": _get_client_id(),
            "client_secret": _get_client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri, "urn:ietf:wg:oauth:2.0:oob"],
        }
    }


def is_configured() -> bool:
    """Return True if OAuth credentials are set in .env. Checked at call time."""
    return bool(_get_client_id() and _get_client_secret())


# ─── OAuth flow ──────────────────────────────────────────────────────────────

def get_auth_url(state: str = "") -> str:
    """Generate the Google OAuth2 authorization URL."""
    from google_auth_oauthlib.flow import Flow

    uri = _redirect_uri()
    flow = Flow.from_client_config(
        _client_config(uri),
        scopes=SCOPES,
        redirect_uri=uri,
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str, redirect_uri: str = "") -> dict:
    """Exchange auth code for tokens. Returns token dict.

    redirect_uri must match the one used in get_auth_url(). Pass it explicitly
    from the callback route so both ends of the flow use the same value.
    """
    from google_auth_oauthlib.flow import Flow

    uri = redirect_uri or _redirect_uri()
    flow = Flow.from_client_config(
        _client_config(uri),
        scopes=SCOPES,
        redirect_uri=uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    return _creds_to_dict(creds)


def _creds_to_dict(creds) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


# ─── Credentials object from stored token ────────────────────────────────────

def _build_credentials(token_dict: dict):
    from google.oauth2.credentials import Credentials

    expiry = None
    if token_dict.get("expiry"):
        try:
            expiry = datetime.fromisoformat(token_dict["expiry"])
            # Make timezone-aware if naive
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    return Credentials(
        token=token_dict.get("token"),
        refresh_token=token_dict.get("refresh_token"),
        token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_dict.get("client_id", _get_client_id()),
        client_secret=token_dict.get("client_secret", _get_client_secret()),
        scopes=token_dict.get("scopes", SCOPES),
        expiry=expiry,
    )


def _refresh_if_needed(creds, token_dict: dict, user_id: int) -> bool:
    """Refresh token if expired, save to DB. Returns True if creds are valid."""
    from google.auth.transport.requests import Request

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token
            _save_token(user_id, _creds_to_dict(creds))
            return True
        except Exception as e:
            log.warning(f"GCal token refresh failed for user {user_id}: {e}")
            return False
    return not creds.expired


def _save_token(user_id: int, token_dict: dict):
    """Persist token JSON to DB."""
    from models import db, GoogleOAuthToken
    existing = GoogleOAuthToken.query.filter_by(user_id=user_id).first()
    if existing:
        existing.token_json = json.dumps(token_dict)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.session.add(GoogleOAuthToken(
            user_id=user_id,
            token_json=json.dumps(token_dict),
        ))
    db.session.commit()


def get_token(user_id: int) -> Optional[dict]:
    """Load token dict from DB for a user."""
    from models import GoogleOAuthToken
    row = GoogleOAuthToken.query.filter_by(user_id=user_id).first()
    if not row:
        return None
    try:
        return json.loads(row.token_json)
    except Exception:
        return None


def disconnect(user_id: int):
    """Remove stored token for user (disconnects Google Calendar)."""
    from models import db, GoogleOAuthToken
    GoogleOAuthToken.query.filter_by(user_id=user_id).delete()
    db.session.commit()


def is_connected(user_id: int) -> bool:
    return get_token(user_id) is not None


# ─── Calendar API calls ───────────────────────────────────────────────────────

def _build_service(user_id: int):
    """Build a Google Calendar API service client for the given user."""
    from googleapiclient.discovery import build

    token_dict = get_token(user_id)
    if not token_dict:
        return None
    creds = _build_credentials(token_dict)
    if not _refresh_if_needed(creds, token_dict, user_id):
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _event_body(ev) -> dict:
    """Convert a CalendarEvent model to a Google Calendar event dict."""
    date_str = ev.date.isoformat() if ev.date else None

    if ev.all_day or not ev.start_time:
        # All-day event
        body = {
            "start": {"date": date_str},
            "end": {"date": date_str},
        }
    else:
        # Timed event
        start_dt = f"{date_str}T{ev.start_time}:00"
        if ev.end_time:
            end_dt = f"{date_str}T{ev.end_time}:00"
        else:
            # Default: 1-hour duration
            from datetime import datetime, timedelta
            st = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%S")
            end_dt = (st + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        tz = "Europe/Madrid"
        body = {
            "start": {"dateTime": start_dt, "timeZone": tz},
            "end": {"dateTime": end_dt, "timeZone": tz},
        }

    # Color mapping
    color_map = {
        "reunion": "9",       # Blueberry
        "evento": "1",        # Lavender
        "recordatorio": "5",  # Banana
    }

    body.update({
        "summary": ev.title,
        "description": ev.description or "",
        "location": ev.location or "",
        "colorId": color_map.get(ev.event_type, "1"),
        "source": {
            "title": "NodexAI Panel",
            "url": "http://localhost:5001/calendario",
        },
    })
    return body


def push_event(ev, user_id: int) -> Optional[str]:
    """
    Create or update a CalendarEvent in Google Calendar.
    Returns the gcal_event_id (str) or None on failure.
    """
    if not is_configured():
        return None

    service = _build_service(user_id)
    if not service:
        return None

    body = _event_body(ev)

    try:
        if ev.gcal_event_id:
            # Update existing
            result = service.events().update(
                calendarId=GCAL_CALENDAR_ID,
                eventId=ev.gcal_event_id,
                body=body,
            ).execute()
        else:
            # Create new
            result = service.events().insert(
                calendarId=GCAL_CALENDAR_ID,
                body=body,
            ).execute()

        gcal_id = result.get("id")
        log.info(f"GCal event synced: {gcal_id} for CalendarEvent {ev.id}")
        return gcal_id

    except Exception as e:
        log.warning(f"GCal push failed for event {ev.id}: {e}")
        return None


def delete_event(gcal_event_id: str, user_id: int) -> bool:
    """Delete an event from Google Calendar. Returns True on success."""
    if not is_configured() or not gcal_event_id:
        return False

    service = _build_service(user_id)
    if not service:
        return False

    try:
        service.events().delete(
            calendarId=GCAL_CALENDAR_ID,
            eventId=gcal_event_id,
        ).execute()
        log.info(f"GCal event deleted: {gcal_event_id}")
        return True
    except Exception as e:
        log.warning(f"GCal delete failed for {gcal_event_id}: {e}")
        return False


def bulk_sync_user(user_id: int) -> Tuple[int, int]:
    """
    Push all CalendarEvents that don't have a gcal_event_id yet.
    Returns (synced_count, failed_count).
    """
    from models import db, CalendarEvent

    if not is_configured() or not is_connected(user_id):
        return 0, 0

    events = CalendarEvent.query.filter_by(gcal_event_id=None).all()
    synced = 0
    failed = 0

    for ev in events:
        gcal_id = push_event(ev, user_id)
        if gcal_id:
            ev.gcal_event_id = gcal_id
            synced += 1
        else:
            failed += 1

    db.session.commit()
    return synced, failed
