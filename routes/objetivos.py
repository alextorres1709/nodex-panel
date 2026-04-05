from datetime import datetime
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, Objective, Project, User
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change

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
            assigned_to=int(aid) if aid else None,
            created_by=g.user.id,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(obj)
        log_activity("create", "objective", details=f"Nuevo objetivo: {obj.title}")
        db.session.commit()
        push_change("objectives", obj.id)
        # Push notification to assigned user
        if aid and int(aid) != g.user.id:
            from services.notifications import notify
            from services.push import send_push
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
        obj.title = request.form.get("title", obj.title).strip()
        obj.description = request.form.get("description", "").strip()
        obj.priority = request.form.get("priority", obj.priority)
        obj.status = request.form.get("status", obj.status)
        obj.progress = int(request.form.get("progress", obj.progress) or 0)
        td = request.form.get("target_date", "").strip()
        obj.target_date = datetime.strptime(td, "%Y-%m-%d").date() if td else None
        pid = request.form.get("project_id", "").strip()
        obj.project_id = int(pid) if pid else None
        aid = request.form.get("assigned_to", "").strip()
        obj.assigned_to = int(aid) if aid else None
        obj.notes = request.form.get("notes", "").strip()
        log_activity("update", "objective", oid, f"Editado: {obj.title}")
        db.session.commit()
        push_change("objectives", oid)
        flash("Objetivo actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("objetivos.index"))


@objetivos_bp.route("/objetivos/delete/<int:oid>", methods=["POST"])
@login_required
def delete(oid):
    obj = db.session.get(Objective, oid)
    if obj:
        obj_id = obj.id
        log_activity("delete", "objective", obj.id, f"Eliminado: {obj.title}")
        db.session.delete(obj)
        db.session.commit()
        push_change("objectives", obj_id)
        flash("Objetivo eliminado", "success")
    return redirect(url_for("objetivos.index"))
