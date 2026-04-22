from datetime import datetime
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from routes.auth import login_required
from services.activity import log_activity
from models import db, Objective, Project, User, ObjectiveSnapshot, ObjectiveAssignment, ObjectiveRequirement, ObjectiveWeeklyPlan
from services.sync import push_change, push_change_now, sync_locked
from services.sync import push_change, push_change_now, sync_locked


def _record_snapshot(obj):
    """Guarda el progreso actual del objetivo en una fila de snapshot."""
    snap = ObjectiveSnapshot(objective_id=obj.id, progress=obj.progress or 0)
    db.session.add(snap)
    db.session.flush()
    push_change("objective_snapshots", snap.id)

objetivos_bp = Blueprint("objetivos", __name__)


@objetivos_bp.route("/objetivos")
@login_required
def index():
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    assigned = request.args.get("assigned_to", "")

    q = Objective.query.options(
        joinedload(Objective.assignee),
        joinedload(Objective.project),
        joinedload(Objective.author),
    )
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if assigned:
        q = q.filter_by(assigned_to=int(assigned))
    objectives = q.order_by(Objective.created_at.desc()).all()

    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).order_by(User.name).all()
    return render_template(
        "objetivos.html",
        objectives=objectives,
        projects=projects,
        users=users,
        sel_status=status,
        sel_priority=priority,
        sel_assigned=assigned,
    )


@objetivos_bp.route("/objetivos/create", methods=["POST"])
@login_required
def create():
    try:
        td = request.form.get("target_date", "").strip()
        pid = request.form.get("project_id", "").strip()
        aid = request.form.get("assigned_to", "").strip()
        obj = Objective(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            priority=request.form.get("priority", "media"),
            status="nuevo",
            progress=int(request.form.get("progress", 0) or 0),
            target_date=datetime.strptime(td, "%Y-%m-%d").date() if td else None,
            project_id=int(pid) if pid else None,
            created_by=g.user.id,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(obj)
        db.session.flush()

        # Multi-assignee
        assignee_ids = request.form.getlist("assigned_to")
        for aid in assignee_ids:
            if str(aid).strip():
                db.session.add(ObjectiveAssignment(objective_id=obj.id, user_id=int(aid)))

        log_activity("create", "objective", details=f"Nuevo objetivo: {obj.title}")
        db.session.commit()
        push_change("objectives", obj.id)

        # Notificar a los asignados
        from services.notifications import notify
        from services.push import send_push
        for aid in assignee_ids:
            if str(aid).strip() and int(aid) != g.user.id:
                notify(int(aid), "objective", f"Nuevo objetivo asignado: {obj.title}",
                       body=f"Prioridad: {obj.priority}", link="/objetivos")
                send_push(int(aid), f"Nuevo objetivo: {obj.title}",
                          body=f"Prioridad: {obj.priority}", link="/objetivos")
        
        flash("Objetivo creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("objetivos.index"))


@objetivos_bp.route("/objetivos/edit/<int:oid>", methods=["POST"])
@login_required
def edit(oid):
    obj = db.session.get(Objective, oid)
    if not obj:
        flash("Objetivo no encontrado", "error")
        return redirect(url_for("objetivos.index"))
    try:
        prev_progress = obj.progress or 0
        obj.title = request.form.get("title", obj.title).strip()
        obj.description = request.form.get("description", "").strip()
        obj.priority = request.form.get("priority", obj.priority)
        obj.status = request.form.get("status", obj.status)
        obj.progress = int(request.form.get("progress", obj.progress) or 0)
        td = request.form.get("target_date", "").strip()
        obj.target_date = datetime.strptime(td, "%Y-%m-%d").date() if td else None
        pid = request.form.get("project_id", "").strip()
        obj.project_id = int(pid) if pid else None
        obj.notes = request.form.get("notes", "").strip()

        # Update assignees
        ObjectiveAssignment.query.filter_by(objective_id=obj.id).delete()
        for aid in request.form.getlist("assigned_to"):
            if str(aid).strip():
                db.session.add(ObjectiveAssignment(objective_id=obj.id, user_id=int(aid)))

        log_activity("update", "objective", oid, f"Editado: {obj.title}")
        if obj.progress != prev_progress:
            _record_snapshot(obj)
        db.session.commit()
        push_change("objectives", oid)
        flash("Objetivo actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("objetivos.index"))


@objetivos_bp.route("/objetivos/<int:oid>")
@login_required
def view(oid):
    obj = db.session.get(Objective, oid)
    if not obj:
        flash("Objetivo no encontrado", "error")
        return redirect(url_for("objetivos.index"))
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).order_by(User.name).all()
    snapshots = obj.snapshots.order_by(ObjectiveSnapshot.created_at.asc()).all()
    return render_template(
        "objetivo_detail.html",
        obj=obj,
        projects=projects,
        users=users,
        snapshots=snapshots,
    )


@objetivos_bp.route("/objetivos/<int:oid>/quick-progress", methods=["POST"])
@login_required
def quick_progress(oid):
    obj = db.session.get(Objective, oid)
    if not obj:
        return jsonify({"error": "not_found"}), 404
    try:
        new = int(request.form.get("progress", 0) or 0)
    except ValueError:
        return jsonify({"error": "invalid"}), 400
    new = max(0, min(100, new))
    prev = obj.progress or 0
    if new != prev:
        obj.progress = new
        if new >= 100 and obj.status != "completado":
            obj.status = "completado"
        elif new > 0 and obj.status == "nuevo":
            obj.status = "en_progreso"
        _record_snapshot(obj)
        log_activity("update", "objective", oid, f"Progreso: {prev}% \u2192 {new}%")
        db.session.commit()
        push_change("objectives", oid)
    return jsonify({"ok": True, "progress": new, "status": obj.status})


@objetivos_bp.route("/objetivos/delete/<int:oid>", methods=["POST"])
@login_required
def delete(oid):
    obj = db.session.get(Objective, oid)
    if obj:
        obj_id = obj.id
        with sync_locked():
            log_activity("delete", "objective", obj.id, f"Eliminado: {obj.title}")
            db.session.delete(obj)
            db.session.commit()
            push_change_now("objectives", obj_id)
        flash("Objetivo eliminado", "success")
    return redirect(url_for("objetivos.index"))


@objetivos_bp.route("/api/objetivos/<int:oid>/snapshots")
@login_required
def api_snapshots(oid):
    """Devuelve la serie temporal del progreso del objetivo (para Chart.js)."""
    obj = db.session.get(Objective, oid)
    if not obj:
        return jsonify({"error": "not found"}), 404
    rows = obj.snapshots.order_by(ObjectiveSnapshot.created_at.asc()).all()
    return jsonify({
        "title": obj.title,
        "current": obj.progress or 0,
        "points": [{
            "date": (s.created_at.isoformat() if s.created_at else None),
            "progress": s.progress or 0,
        } for s in rows],
    })

@objetivos_bp.route("/objetivos/<int:oid>/requirements", methods=["POST"])
@login_required
def add_requirement(oid):
    req = ObjectiveRequirement(
        objective_id=oid,
        title=request.form.get("title", "").strip(),
        description=request.form.get("description", "").strip(),
    )
    db.session.add(req)
    db.session.commit()
    flash("Requisito añadido", "success")
    return redirect(url_for("objetivos.view", oid=oid))

@objetivos_bp.route("/objetivos/<int:oid>/requirements/<int:req_id>/toggle", methods=["POST"])
@login_required
def toggle_requirement(oid, req_id):
    req = db.session.get(ObjectiveRequirement, req_id)
    if req and req.objective_id == oid:
        req.is_met = not req.is_met
        db.session.commit()
    return jsonify({"ok": True, "is_met": req.is_met})

@objetivos_bp.route("/objetivos/<int:oid>/requirements/<int:req_id>/delete", methods=["POST"])
@login_required
def delete_requirement(oid, req_id):
    req = db.session.get(ObjectiveRequirement, req_id)
    if req and req.objective_id == oid:
        db.session.delete(req)
        db.session.commit()
        flash("Requisito eliminado", "success")
    return redirect(url_for("objetivos.view", oid=oid))

@objetivos_bp.route("/objetivos/<int:oid>/weekly_plans", methods=["POST"])
@login_required
def add_weekly_plan(oid):
    ws = request.form.get("week_start", "").strip()
    plan = ObjectiveWeeklyPlan(
        objective_id=oid,
        week_start=datetime.strptime(ws, "%Y-%m-%d").date() if ws else datetime.utcnow().date(),
        focus=request.form.get("focus", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(plan)
    db.session.commit()
    flash("Plan semanal añadido", "success")
    return redirect(url_for("objetivos.view", oid=oid))

@objetivos_bp.route("/objetivos/<int:oid>/weekly_plans/<int:plan_id>/delete", methods=["POST"])
@login_required
def delete_weekly_plan(oid, plan_id):
    plan = db.session.get(ObjectiveWeeklyPlan, plan_id)
    if plan and plan.objective_id == oid:
        db.session.delete(plan)
        db.session.commit()
        flash("Plan semanal eliminado", "success")
    return redirect(url_for("objetivos.view", oid=oid))
