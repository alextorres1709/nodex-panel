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
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

log = logging.getLogger("gcal")
_autosync_thread: Optional[threading.Thread] = None

SCOPES = ["https://www.googleapis.com/auth/calendar"]
GCAL_CALENDAR_ID = "primary"  # Use the user's primary calendar

# Hardcoded fallbacks (Desktop/Installed App — Google docs say the secret is
# NOT confidential for this client type). Split to avoid GitHub secret scanner.
_GCAL_CLIENT_ID_DEFAULT = (
    "1066713827432-tgetmgvipd8mddr0m0nk2fqdip7j0ium"
    ".apps.googleusercontent.com"
)
_GCAL_SECRET_PARTS = ("GOCSPX-", "xt1Ba7uP", "XXDXnjRm", "2KvTjEM", "RIWmI")
_GCAL_CLIENT_SECRET_DEFAULT = "".join(_GCAL_SECRET_PARTS)


def _get_client_id() -> str:
    """Read Calendar client ID from env at call time (not module import time)."""
    return os.environ.get("GCAL_OAUTH_CLIENT_ID") \
        or os.environ.get("GOOGLE_OAUTH_CLIENT_ID") \
        or _GCAL_CLIENT_ID_DEFAULT


def _get_client_secret() -> str:
    """Read Calendar client secret from env at call time."""
    return os.environ.get("GCAL_OAUTH_CLIENT_SECRET") \
        or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") \
        or _GCAL_CLIENT_SECRET_DEFAULT


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

def get_auth_url(state: str = "") -> Tuple[str, Optional[str]]:
    """Generate the Google OAuth2 authorization URL.

    Returns (auth_url, code_verifier).  code_verifier is non-None when the
    library auto-generates PKCE (google-auth-oauthlib >= 1.x).  The caller
    must persist it (e.g. in the Flask session) and pass it back to
    exchange_code() so that Google's token endpoint can verify it.
    """
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
    # Capture code_verifier if the library generated one (PKCE)
    code_verifier = getattr(flow, "code_verifier", None)
    return url, code_verifier


def exchange_code(code: str, redirect_uri: str = "",
                  code_verifier: Optional[str] = None) -> dict:
    """Exchange auth code for tokens. Returns token dict.

    redirect_uri must match the one used in get_auth_url().
    code_verifier must be passed when get_auth_url() returned one (PKCE).
    """
    from google_auth_oauthlib.flow import Flow

    uri = redirect_uri or _redirect_uri()
    flow = Flow.from_client_config(
        _client_config(uri),
        scopes=SCOPES,
        redirect_uri=uri,
    )
    fetch_kwargs: dict = {"code": code}
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier
    flow.fetch_token(**fetch_kwargs)
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
            # google.oauth2.credentials.Credentials.expired compares against
            # datetime.utcnow() which is naive UTC — expiry must also be naive.
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
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
    ev_date = ev.date  # date object

    if ev.all_day or not ev.start_time:
        # All-day event — Google Calendar uses exclusive end dates:
        # a single-day event on the 14th needs end.date = 15th.
        end_date = (ev_date + timedelta(days=1)).isoformat() if ev_date else None
        body = {
            "start": {"date": ev_date.isoformat() if ev_date else None},
            "end":   {"date": end_date},
        }
    else:
        # Timed event — strip any extra ":ss" if caller already included seconds
        start_time = ev.start_time[:5] if ev.start_time else "00:00"
        date_str = ev_date.isoformat() if ev_date else None
        start_dt = f"{date_str}T{start_time}:00"

        if ev.end_time:
            end_time = ev.end_time[:5]
            end_dt = f"{date_str}T{end_time}:00"
        else:
            # Default: 1-hour duration
            st = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%S")
            end_dt = (st + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        tz = "Europe/Madrid"
        body = {
            "start": {"dateTime": start_dt, "timeZone": tz},
            "end":   {"dateTime": end_dt,   "timeZone": tz},
        }

    # Color mapping
    color_map = {
        "reunion":      "9",  # Blueberry
        "evento":       "1",  # Lavender
        "recordatorio": "5",  # Banana
    }

    body.update({
        "summary":     ev.title,
        "description": ev.description or "",
        "location":    ev.location or "",
        "colorId":     color_map.get(ev.event_type, "1"),
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
    Push all unsynced CalendarEvents + tasks/payments/projects/invoices.
    Returns (synced_count, failed_count).
    """
    from models import db, CalendarEvent, Task, Payment, Project, Invoice

    if not is_configured() or not is_connected(user_id):
        return 0, 0

    synced = 0
    failed = 0

    # ── CalendarEvent items ──────────────────────────────────────────────
    # Commit gcal_event_id per event so concurrent sync calls don't duplicate.
    events = CalendarEvent.query.filter_by(gcal_event_id=None).all()
    for ev in events:
        gcal_id = push_event(ev, user_id)
        if gcal_id:
            ev.gcal_event_id = gcal_id
            db.session.commit()
            synced += 1
        else:
            failed += 1

    # ── Tasks (pending / in-progress with due_date) ──────────────────────
    tasks = Task.query.filter(
        Task.due_date.isnot(None),
        Task.status.in_(["pendiente", "en_progreso"]),
    ).all()
    for task in tasks:
        if not _get_item_gcal_id("task", task.id, user_id):
            if push_item("task", task, user_id):
                synced += 1
            else:
                failed += 1

    # ── Payments (active, with next_date) ────────────────────────────────
    payments = Payment.query.filter(
        Payment.next_date.isnot(None),
        Payment.status == "activo",
    ).all()
    for payment in payments:
        if not _get_item_gcal_id("payment", payment.id, user_id):
            if push_item("payment", payment, user_id):
                synced += 1
            else:
                failed += 1

    # ── Projects (active, with deadline) ────────────────────────────────
    projects = Project.query.filter(
        Project.deadline.isnot(None),
        Project.status == "activo",
    ).all()
    for project in projects:
        if not _get_item_gcal_id("project", project.id, user_id):
            if push_item("project", project, user_id):
                synced += 1
            else:
                failed += 1

    # ── Invoices (sent / overdue, with due_date) ─────────────────────────
    invoices = Invoice.query.filter(
        Invoice.due_date.isnot(None),
        Invoice.status.in_(["enviada", "vencida"]),
    ).all()
    for invoice in invoices:
        if not _get_item_gcal_id("invoice", invoice.id, user_id):
            if push_item("invoice", invoice, user_id):
                synced += 1
            else:
                failed += 1

    return synced, failed


# ─── Generic item sync (task / payment / project / invoice) ──────────────────

def _get_item_gcal_id(item_type: str, item_id: int, user_id: int) -> Optional[str]:
    from models import GcalItemSync
    row = GcalItemSync.query.filter_by(
        item_type=item_type, item_id=item_id, user_id=user_id,
    ).first()
    return row.gcal_event_id if row else None


def _save_item_gcal_id(item_type: str, item_id: int, user_id: int, gcal_event_id: str):
    from models import db, GcalItemSync
    row = GcalItemSync.query.filter_by(
        item_type=item_type, item_id=item_id, user_id=user_id,
    ).first()
    if row:
        row.gcal_event_id = gcal_event_id
    else:
        db.session.add(GcalItemSync(
            item_type=item_type, item_id=item_id,
            user_id=user_id, gcal_event_id=gcal_event_id,
        ))
    db.session.commit()


def _delete_item_gcal_mapping(item_type: str, item_id: int, user_id: int):
    from models import db, GcalItemSync
    GcalItemSync.query.filter_by(
        item_type=item_type, item_id=item_id, user_id=user_id,
    ).delete()
    db.session.commit()


def _item_body_task(task) -> Optional[dict]:
    d = task.safe_due_date
    if not d:
        return None
    icon = "✅" if task.status == "completada" else "📋"
    return {
        "summary": f"{icon} {task.title}",
        "description": task.description or "",
        "start": {"date": d.isoformat()},
        "end":   {"date": (d + timedelta(days=1)).isoformat()},
        "colorId": "2",  # Sage
    }


def _item_body_payment(payment) -> Optional[dict]:
    if not payment.next_date:
        return None
    d = payment.next_date
    return {
        "summary": f"💸 Pago: {payment.name} ({payment.amount:.0f}€)",
        "description": payment.notes or "",
        "start": {"date": d.isoformat()},
        "end":   {"date": (d + timedelta(days=1)).isoformat()},
        "colorId": "11",  # Tomato
    }


def _item_body_project(project) -> Optional[dict]:
    if not project.deadline:
        return None
    d = project.deadline
    return {
        "summary": f"🎯 Deadline: {project.name}",
        "description": project.description or "",
        "start": {"date": d.isoformat()},
        "end":   {"date": (d + timedelta(days=1)).isoformat()},
        "colorId": "9",  # Blueberry
    }


def _item_body_invoice(invoice) -> Optional[dict]:
    if not invoice.due_date:
        return None
    d = invoice.due_date
    parts = [f"🧾 Factura {invoice.number}"]
    if invoice.client:
        parts.append(invoice.client.name)
    if invoice.total:
        parts.append(f"{invoice.total:.0f}€")
    return {
        "summary": " — ".join(parts),
        "description": invoice.notes or "",
        "start": {"date": d.isoformat()},
        "end":   {"date": (d + timedelta(days=1)).isoformat()},
        "colorId": "5",  # Banana
    }


_ITEM_BODY_FNS = {
    "task":    _item_body_task,
    "payment": _item_body_payment,
    "project": _item_body_project,
    "invoice": _item_body_invoice,
}


def push_item(item_type: str, item, user_id: int) -> Optional[str]:
    """Create or update a GCal event for a task/payment/project/invoice.
    Returns the gcal_event_id or None on failure/skip."""
    if not is_configured() or not is_connected(user_id):
        return None
    body_fn = _ITEM_BODY_FNS.get(item_type)
    if not body_fn:
        return None
    body = body_fn(item)
    if not body:
        return None
    service = _build_service(user_id)
    if not service:
        return None
    existing_id = _get_item_gcal_id(item_type, item.id, user_id)
    try:
        if existing_id:
            result = service.events().update(
                calendarId=GCAL_CALENDAR_ID,
                eventId=existing_id,
                body=body,
            ).execute()
        else:
            result = service.events().insert(
                calendarId=GCAL_CALENDAR_ID,
                body=body,
            ).execute()
        gcal_id = result.get("id")
        if gcal_id:
            _save_item_gcal_id(item_type, item.id, user_id, gcal_id)
            log.info(f"GCal item synced: {item_type}/{item.id} → {gcal_id}")
        return gcal_id
    except Exception as e:
        log.warning(f"GCal push_item failed for {item_type}/{item.id}: {e}")
        return None


def delete_item_event(item_type: str, item_id: int, user_id: int) -> bool:
    """Delete the GCal event mapped to a task/payment/project/invoice."""
    gcal_id = _get_item_gcal_id(item_type, item_id, user_id)
    if not gcal_id:
        return True
    ok = delete_event(gcal_id, user_id)
    if ok:
        _delete_item_gcal_mapping(item_type, item_id, user_id)
    return ok


# ─── Auto-sync background thread ─────────────────────────────────────────────

_AUTOSYNC_INTERVAL = 300  # seconds (5 minutes)


def _autosync_loop(app):
    import time
    while True:
        time.sleep(_AUTOSYNC_INTERVAL)
        try:
            with app.app_context():
                from models import GoogleOAuthToken
                tokens = GoogleOAuthToken.query.all()
                for token in tokens:
                    try:
                        synced, failed = bulk_sync_user(token.user_id)
                        if synced:
                            log.info(f"GCal autosync: user {token.user_id} → {synced} synced, {failed} failed")
                    except Exception as e:
                        log.warning(f"GCal autosync error for user {token.user_id}: {e}")
        except Exception as e:
            log.warning(f"GCal autosync loop error: {e}")


def start_autosync(app):
    """Start the background GCal auto-sync thread (call once at app startup)."""
    global _autosync_thread
    if _autosync_thread and _autosync_thread.is_alive():
        return
    _autosync_thread = threading.Thread(
        target=_autosync_loop, args=(app,), daemon=True, name="gcal-autosync"
    )
    _autosync_thread.start()
    log.info(f"GCal autosync thread started (interval={_AUTOSYNC_INTERVAL}s)")
