"""
Presence tracking using User DB model with auto-sync capability.
Tracks which users are online and whether they're time-tracking.
"""
import time
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("presence")

ONLINE_TIMEOUT = 60  # seconds before a user is considered offline


def heartbeat(user_id, name, is_tracking=False, tracking_started=None):
    """Update presence state for a user in the database."""
    from models import db, User
    from services.sse import sse_bus
    from services.sync import push_change_now

    user = db.session.get(User, user_id)
    if user:
        user.last_seen_at = datetime.now(timezone.utc)
        user.is_tracking = is_tracking
        user.tracking_started = tracking_started
        db.session.commit()
        push_change_now("users", user.id)

    sse_bus.publish("presence", _get_snapshot())


def mark_offline(user_id):
    """Mark a user offline in the database."""
    from models import db, User
    from services.sse import sse_bus
    from services.sync import push_change_now

    user = db.session.get(User, user_id)
    if user:
        user.last_seen_at = None
        db.session.commit()
        push_change_now("users", user.id)

    sse_bus.publish("presence", _get_snapshot())


def get_online_users():
    """Return list of users seen within ONLINE_TIMEOUT."""
    from models import User
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ONLINE_TIMEOUT)
    users = User.query.filter(User.last_seen_at >= cutoff).all()
    
    return [
        {
            "user_id": u.id,
            "name": u.name,
            "is_tracking": u.is_tracking,
            "tracking_started": u.tracking_started,
        }
        for u in users
    ]


def _get_snapshot():
    """Build presence snapshot for SSE broadcast."""
    return {"users": get_online_users()}
