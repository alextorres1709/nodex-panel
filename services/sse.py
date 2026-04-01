"""
Server-Sent Events (SSE) pub/sub bus.
Thread-safe in-memory bus that allows the sync engine and other services
to push events to all connected browser clients instantly.
"""
import json
import queue
import threading
import logging

log = logging.getLogger("sse")


class SSEBus:
    """Thread-safe publish/subscribe bus for SSE connections."""

    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self):
        """Create a new subscriber queue. Returns the queue."""
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        """Remove a subscriber queue."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event, data=None):
        """Publish an event to all subscribers (non-blocking)."""
        msg = {"event": event, "data": data or {}}
        with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

    @property
    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)


# Singleton instance used across the app
sse_bus = SSEBus()
