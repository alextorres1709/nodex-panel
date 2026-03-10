import hashlib
import json
import time
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, Response, jsonify
from models import db, Message, CallSession, Project, User
from routes.auth import login_required
from services.activity import log_activity

cowork_bp = Blueprint("cowork", __name__)

# Fixed voice channels (like Discord)
VOICE_CHANNELS = [
    {"id": "trabajando-1", "name": "Trabajando 1"},
    {"id": "trabajando-2", "name": "Trabajando 2"},
]


@cowork_bp.route("/cowork")
@cowork_bp.route("/cowork/<channel>")
@login_required
def index(channel="general"):
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).all()
    messages = (
        Message.query
        .options(joinedload(Message.sender))
        .filter_by(channel=channel)
        .order_by(Message.created_at.asc())
        .limit(200)
        .all()
    )
    active_calls = CallSession.query.options(joinedload(CallSession.creator)).filter_by(ended_at=None).all()

    # Build dict: room_name -> list of users in that room
    voice_rooms = {}
    for vc in VOICE_CHANNELS:
        voice_rooms[vc["id"]] = []
    for c in active_calls:
        if c.room_name in voice_rooms:
            voice_rooms[c.room_name].append(c)

    return render_template(
        "cowork.html",
        channel=channel,
        messages=messages,
        projects=projects,
        users=users,
        voice_channels=VOICE_CHANNELS,
        voice_rooms=voice_rooms,
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

    # Notify other users about the new message
    from services.notifications import notify_all_except
    preview = msg.content[:80] + ("..." if len(msg.content) > 80 else "")
    notify_all_except(
        sender_id=g.user.id,
        type="message",
        title=f"{g.user.name}: {preview}",
        body=msg.content,
        link="/cowork",
    )

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
            # Refresh session to see new messages committed by other requests
            db.session.commit()
            
            msgs = (
                Message.query
                .options(joinedload(Message.sender))
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
            yield ": heartbeat\n\n"
            time.sleep(2)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@cowork_bp.route("/cowork/voice/join/<room_id>", methods=["POST"])
@login_required
def join_voice(room_id):
    # Check if user is already actively calling anywhere
    active_calls = CallSession.query.filter_by(created_by=g.user.id, ended_at=None).all()
    
    existing_call = None
    for call in active_calls:
        if call.room_name == room_id:
            existing_call = call
        else:
            # End calls in other rooms
            call.ended_at = datetime.now(timezone.utc)
            
    if existing_call:
        # User is already in this exact room, just return it without creating duplicate
        call = existing_call
        db.session.commit()
    else:
        # Create new session in this room
        call = CallSession(
            room_name=room_id,
            created_by=g.user.id,
        )
        db.session.add(call)
        log_activity("create", "call", details=f"Unido a canal de voz: {room_id}")
        db.session.commit()

    # Generate unique Jitsi room name to avoid auth requirement on meet.jit.si
    room_hash = hashlib.sha256(f"nodexai-panel-{room_id}".encode()).hexdigest()[:12]
    jitsi_room = f"NdxAi{room_id.title().replace('-','')}{room_hash}"
    return jsonify({"room": jitsi_room, "call_id": call.id})


@cowork_bp.route("/cowork/voice/leave", methods=["POST"])
@login_required
def leave_voice():
    # End all active calls for this user
    active = CallSession.query.filter_by(created_by=g.user.id, ended_at=None).all()
    for c in active:
        c.ended_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"ok": True})


@cowork_bp.route("/cowork/call/<room>")
@login_required
def call(room):
    return render_template("cowork_call.html", room=room)
