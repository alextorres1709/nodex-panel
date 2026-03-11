import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db, Automation
from routes.auth import login_required
from services.activity import log_activity

automations_bp = Blueprint("automations", __name__)


@automations_bp.route("/automatizaciones")
@login_required
def index():
    automations = Automation.query.order_by(Automation.created_at.desc()).all()
    return render_template("automatizaciones.html", automations=automations)


@automations_bp.route("/automatizaciones/create", methods=["POST"])
@login_required
def create():
    uid = session.get("user_id")
    try:
        trigger_config = {
            "event": request.form.get("trigger_event", ""),
            "condition": request.form.get("trigger_condition", ""),
        }
        action_config = {
            "target": request.form.get("action_target", ""),
            "value": request.form.get("action_value", ""),
        }
        auto = Automation(
            name=request.form.get("name", "").strip(),
            trigger_type=request.form.get("trigger_type", "event"),
            trigger_config=json.dumps(trigger_config),
            action_type=request.form.get("action_type", "notify"),
            action_config=json.dumps(action_config),
            active=True,
            created_by=uid,
        )
        db.session.add(auto)
        log_activity("create", "automation", details=f"Nueva: {auto.name}")
        db.session.commit()
        flash("Automatización creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("automations.index"))


@automations_bp.route("/automatizaciones/<int:aid>/toggle", methods=["POST"])
@login_required
def toggle(aid):
    auto = db.session.get(Automation, aid)
    if auto:
        auto.active = not auto.active
        log_activity("update", "automation", auto.id,
                     f"{'Activada' if auto.active else 'Desactivada'}: {auto.name}")
        db.session.commit()
    return redirect(url_for("automations.index"))


@automations_bp.route("/automatizaciones/<int:aid>/delete", methods=["POST"])
@login_required
def delete(aid):
    auto = db.session.get(Automation, aid)
    if auto:
        log_activity("delete", "automation", auto.id, f"Eliminada: {auto.name}")
        db.session.delete(auto)
        db.session.commit()
        flash("Automatización eliminada", "success")
    return redirect(url_for("automations.index"))


@automations_bp.route("/api/automations/<int:aid>/run", methods=["POST"])
@login_required
def run_manual(aid):
    """Manually trigger an automation."""
    from services.notifications import notify
    auto = db.session.get(Automation, aid)
    if not auto:
        return jsonify({"error": "not found"}), 404

    action_config = json.loads(auto.action_config) if auto.action_config else {}

    if auto.action_type == "notify":
        from models import User
        users = User.query.filter_by(active=True).all()
        for u in users:
            notify(u.id, "system", f"[Auto] {auto.name}", action_config.get("value", ""))
    elif auto.action_type == "create_task":
        from models import Task
        task = Task(
            title=action_config.get("value", f"Tarea auto: {auto.name}"),
            status="pendiente",
            priority="media",
        )
        db.session.add(task)

    auto.run_count += 1
    from datetime import datetime, timezone
    auto.last_run = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"ok": True, "run_count": auto.run_count})
