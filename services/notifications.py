"""
Notification service — creates notifications for users.
Used by messages, tasks, payments, and future APK push.
"""
from models import db, Notification


def notify(user_id, type, title, body="", link=""):
    """Create a notification for a user."""
    n = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
    )
    db.session.add(n)
    db.session.commit()
    return n


def notify_all_except(sender_id, type, title, body="", link=""):
    """Create a notification for ALL users except the sender."""
    from models import User
    users = User.query.filter(User.id != sender_id, User.active == True).all()
    for u in users:
        n = Notification(
            user_id=u.id, type=type, title=title, body=body, link=link
        )
        db.session.add(n)
    db.session.commit()


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
