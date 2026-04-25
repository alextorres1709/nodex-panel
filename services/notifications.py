"""
Notification service — creates notifications for users.
Also sends FCM push notifications to Android/iOS devices.
"""
from models import db, Notification


def _push(user_id, title, body, link):
    """Send FCM push (non-blocking). Silently ignores if FCM is not configured."""
    try:
        from services.push import send_push
        send_push(user_id, title, body, link)
    except Exception:
        pass


def notify(user_id, type, title, body="", link=""):
    """Create a notification for a user and send FCM push."""
    n = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
    )
    db.session.add(n)
    db.session.commit()
    _push(user_id, title, body, link)
    try:
        from services.sse import sse_bus
        count = get_unread_count(user_id)
        sse_bus.publish("notification", {
            "count": count,
            "title": title,
            "body": body,
            "type": type,
            "link": link,
            "id": n.id
        })
    except Exception:
        pass
    return n


def notify_all_except(sender_id, type, title, body="", link=""):
    """Create a notification for ALL users except the sender + FCM push."""
    from models import User
    users = User.query.filter(User.id != sender_id, User.active == True).all()
    for u in users:
        n = Notification(
            user_id=u.id, type=type, title=title, body=body, link=link
        )
        db.session.add(n)
    db.session.commit()
    for u in users:
        _push(u.id, title, body, link)


def get_unread_count(user_id):
    """Get count of unread notifications."""
    return Notification.query.filter_by(user_id=user_id, read=False).count()


def get_recent(user_id, limit=20):
    """Get recent notifications for a user."""
    return (
        Notification.query
        .filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def mark_read(notification_id, user_id):
    """Mark a single notification as read."""
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if n:
        n.read = True
        db.session.commit()


def mark_all_read(user_id):
    """Mark all notifications as read for a user."""
    Notification.query.filter_by(user_id=user_id, read=False).update({"read": True})
    db.session.commit()
