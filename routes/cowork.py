import json
import time
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, Response, jsonify
from models import db, Message, CallSession, Project, User
from routes.auth import login_required
from services.activity import log_activity

cowork_bp = Blueprint("cowork", __name__)


@cowork_bp.route("/cowork")
@cowork_bp.route("/cowork/<channel>")
@login_required
def index(channel="general"):
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).all()
    messages = (
        Message.query
        .filter_by(channel=channel)
        .order_by(Message.created_at.asc())
        .limit(200)
        .all()
    )
    calls = (
        CallSession.query
        .filter_by(ended_at=None)
        .order_by(CallSession.started_at.desc())
        .all()
    )
    return render_template(
        "cowork.html",
        channel=channel,
        messages=messages,
        projects=projects,
        users=users,
        active_calls=calls,
    )


@cowork_bp.route("/cowork/send", methods=["POST"])
@login_required
def send():
    data = request.get_json()
    if not data or not data.get("content", "").strip():
        return jsonify({"error": "Mensaje vacio"}), 400
    msg = Message(
        sender_id=g.user.id,
        channel=data.get("channel", "general"),
        content=data["content"].strip(),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({
        "id": msg.id,
        "sender": g.user.name,
        "content": msg.content,
        "channel": msg.channel,
        "created_at": msg.created_at.isoformat(),
    })


@cowork_bp.route("/cowork/stream")
@login_required
def stream():
    channel = request.args.get("channel", "general")
    last_id = int(request.args.get("last_id", 0))

    def generate():
        nonlocal last_id
        while True:
            msgs = (
                Message.query
                .filter(Message.channel == channel, Message.id > last_id)
                .order_by(Message.id.asc())
                .all()
            )
            for m in msgs:
                last_id = m.id
                data = json.dumps({
                    "id": m.id,
                    "sender": m.sender.name if m.sender else "?",
                    "sender_id": m.sender_id,
                    "content": m.content,
                    "created_at": m.created_at.strftime("%H:%M"),
                })
                yield f"data: {data}\n\n"
            # Keep-alive
            yield ": heartbeat\n\n"
            time.sleep(2)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@cowork_bp.route("/cowork/call/start", methods=["POST"])
@login_required
def start_call():
    data = request.get_json() or {}
    pid = data.get("project_id")
    room = f"nodexai-{g.user.name.lower()}-{int(time.time())}"
    call = CallSession(
        room_name=room,
        project_id=int(pid) if pid else None,
        created_by=g.user.id,
    )
    db.session.add(call)
    log_activity("create", "call", details=f"Videollamada: {room}")
    db.session.commit()
    return jsonify({"room": room, "call_id": call.id})


@cowork_bp.route("/cowork/call/<room>")
@login_required
def call(room):
    return render_template("cowork_call.html", room=room)


@cowork_bp.route("/cowork/call/end/<int:call_id>", methods=["POST"])
@login_required
def end_call(call_id):
    c = db.session.get(CallSession, call_id)
    if c and not c.ended_at:
        c.ended_at = datetime.now(timezone.utc)
        db.session.commit()
    return jsonify({"ok": True})
