from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, Task, User, Project
from routes.auth import login_required
from services.activity import log_activity

tasks_bp = Blueprint("tasks", __name__)


def _run_in_app(app, fn):
    with app.app_context():
        return fn()


@tasks_bp.route("/tareas")
@login_required
def index():
    app = current_app._get_current_object()
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    assigned = request.args.get("assigned_to", "")

    def q_tasks():
        q = Task.query.options(joinedload(Task.assignee), joinedload(Task.project))
        if status:
            q = q.filter_by(status=status)
        if priority:
            q = q.filter_by(priority=priority)
        if assigned:
            q = q.filter_by(assigned_to=int(assigned))
        return q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    def q_users():
        return User.query.filter_by(active=True).all()

    def q_projects():
        return Project.query.order_by(Project.name).all()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_tasks = pool.submit(_run_in_app, app, q_tasks)
        f_users = pool.submit(_run_in_app, app, q_users)
        f_projects = pool.submit(_run_in_app, app, q_projects)

    tasks = f_tasks.result()
    users = f_users.result()
    projects = f_projects.result()
    return render_template("tareas.html", tasks=tasks, users=users, projects=projects,
                           sel_status=status, sel_priority=priority, sel_assigned=assigned)


@tasks_bp.route("/tareas/create", methods=["POST"])
@login_required
def create():
    try:
        dd = request.form.get("due_date", "").strip()
        at = request.form.get("assigned_to", "").strip()
        pid = request.form.get("project_id", "").strip()
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            assigned_to=int(at) if at else None,
            priority=request.form.get("priority", "media"),
            status=request.form.get("status", "pendiente"),
            due_date=datetime.strptime(dd, "%Y-%m-%d").date() if dd else None,
            project_id=int(pid) if pid else None,
        )
        db.session.add(t)
        log_activity("create", "task", details=f"Nueva tarea: {t.title}")
        db.session.commit()
        flash("Tarea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/edit/<int:tid>", methods=["POST"])
@login_required
def edit(tid):
    t = db.session.get(Task, tid)
    if not t:
        flash("Tarea no encontrada", "error")
        return redirect(url_for("tasks.index"))
    try:
        t.title = request.form.get("title", t.title).strip()
        t.description = request.form.get("description", "").strip()
        at = request.form.get("assigned_to", "").strip()
        t.assigned_to = int(at) if at else None
        t.priority = request.form.get("priority", t.priority)
        t.status = request.form.get("status", t.status)
        dd = request.form.get("due_date", "").strip()
        t.due_date = datetime.strptime(dd, "%Y-%m-%d").date() if dd else None
        pid = request.form.get("project_id", "").strip()
        t.project_id = int(pid) if pid else None
        log_activity("update", "task", t.id, f"Editada: {t.title}")
        db.session.commit()
        flash("Tarea actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/toggle/<int:tid>", methods=["POST"])
@login_required
def toggle(tid):
    t = db.session.get(Task, tid)
    if t:
        t.status = "completada" if t.status != "completada" else "pendiente"
        log_activity("update", "task", t.id, f"{'Completada' if t.status == 'completada' else 'Reabierta'}: {t.title}")
        db.session.commit()
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/delete/<int:tid>", methods=["POST"])
@login_required
def delete(tid):
    t = db.session.get(Task, tid)
    if t:
        log_activity("delete", "task", t.id, f"Eliminada: {t.title}")
        db.session.delete(t)
        db.session.commit()
        flash("Tarea eliminada", "success")
    return redirect(url_for("tasks.index"))
