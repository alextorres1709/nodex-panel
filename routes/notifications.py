from flask import Blueprint, jsonify, session, request
from models import db, Notification
from routes.auth import login_required
from services.notifications import get_unread_count, get_recent, mark_read, mark_all_read

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/api/notifications")
@login_required
def list_notifications():
    uid = session.get("user_id")
    notifs = get_recent(uid, limit=30)
    return jsonify({
        "unread": get_unread_count(uid),
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "read": n.read,
                "created_at": n.created_at.strftime("%d/%m %H:%M"),
            }
            for n in notifs
        ],
    })


@notifications_bp.route("/api/notifications/unread-count")
@login_required
def unread_count():
    uid = session.get("user_id")
    return jsonify({"count": get_unread_count(uid)})


@notifications_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def read_one(nid):
    uid = session.get("user_id")
    mark_read(nid, uid)
    return jsonify({"ok": True})


@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required
def read_all():
    uid = session.get("user_id")
    mark_all_read(uid)
    return jsonify({"ok": True})
