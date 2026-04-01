"""
In-memory presence tracking with SSE broadcasting.
Tracks which users are online and whether they're time-tracking.
"""
import time
import threading
import logging

log = logging.getLogger("presence")

_presence = {}
_lock = threading.Lock()

ONLINE_TIMEOUT = 60  # seconds before a user is considered offline


def heartbeat(user_id, name, is_tracking=False, tracking_started=None):
    """Update presence state for a user and broadcast via SSE."""
    from services.sse import sse_bus

    with _lock:
        _presence[user_id] = {
            "user_id": user_id,
            "name": name,
            "last_seen": time.time(),
            "is_tracking": is_tracking,
            "tracking_started": tracking_started,
        }

    sse_bus.publish("presence", _get_snapshot())


def mark_offline(user_id):
    """Remove a user from presence and broadcast."""
    from services.sse import sse_bus

    with _lock:
        _presence.pop(user_id, None)

    sse_bus.publish("presence", _get_snapshot())


def get_online_users():
    """Return list of users seen within ONLINE_TIMEOUT."""
    cutoff = time.time() - ONLINE_TIMEOUT
    with _lock:
        return [
            {
                "user_id": p["user_id"],
                "name": p["name"],
                "is_tracking": p["is_tracking"],
                "tracking_started": p["tracking_started"],
            }
            for p in _presence.values()
            if p["last_seen"] >= cutoff
        ]


def _get_snapshot():
    """Build presence snapshot for SSE broadcast."""
    return {"users": get_online_users()}
