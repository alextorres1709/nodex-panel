from datetime import datetime, date
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Task, Subtask, User, Project
from routes.auth import login_required
from services.activity import log_activity

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/tareas")
@login_required
def index():
    view = request.args.get("view", "kanban")
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    assigned = request.args.get("assigned_to", "")

    q = Task.query.options(joinedload(Task.assignee), joinedload(Task.project))
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if assigned:
        q = q.filter_by(assigned_to=int(assigned))
    tasks = q.order_by(Task.kanban_order.asc(), Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    # Group by status for Kanban
    kanban = {
        "pendiente": [t for t in tasks if t.status == "pendiente"],
        "en_progreso": [t for t in tasks if t.status == "en_progreso"],
        "completada": [t for t in tasks if t.status == "completada"],
    }

    users = User.query.filter_by(active=True).all()
    projects = Project.query.order_by(Project.name).all()

    return render_template("tareas.html", tasks=tasks, kanban=kanban, users=users, projects=projects,
                           sel_status=status, sel_priority=priority, sel_assigned=assigned, view=view,
                           today=date.today())


@tasks_bp.route("/tareas/create", methods=["POST"])
@login_required
def create():
    try:
        dd = request.form.get("due_date", "").strip()
        at = request.form.get("assigned_to", "").strip()
        pid = request.form.get("project_id", "").strip()
        em = request.form.get("estimated_minutes", "").strip()
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            assigned_to=int(at) if at else None,
            priority=request.form.get("priority", "media"),
            status=request.form.get("status", "pendiente"),
            due_date=datetime.strptime(dd, "%Y-%m-%d").date() if dd else None,
            project_id=int(pid) if pid else None,
            estimated_minutes=int(em) if em else 0,
        )
        db.session.add(t)
        db.session.flush()

        # Subtasks
        sub_titles = request.form.getlist("subtask_title")
        for st in sub_titles:
            st = st.strip()
            if st:
                db.session.add(Subtask(task_id=t.id, title=st))

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
        em = request.form.get("estimated_minutes", "").strip()
        t.estimated_minutes = int(em) if em else 0
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


# ═══ KANBAN API (drag & drop) ═══

@tasks_bp.route("/api/tasks/<int:tid>/move", methods=["POST"])
@login_required
def api_move(tid):
    """Move task to a new status/position (Kanban drag & drop)."""
    t = db.session.get(Task, tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    new_status = data.get("status", t.status)
    new_order = data.get("order", t.kanban_order)
    if new_status in ("pendiente", "en_progreso", "completada"):
        t.status = new_status
    t.kanban_order = new_order
    log_activity("update", "task", t.id, f"Movida a {t.status}: {t.title}")
    db.session.commit()
    return jsonify({"ok": True, "status": t.status, "order": t.kanban_order})


# ═══ SUBTASK API ═══

@tasks_bp.route("/api/tasks/<int:tid>/subtasks", methods=["POST"])
@login_required
def api_add_subtask(tid):
    t = db.session.get(Task, tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    st = Subtask(task_id=tid, title=title)
    db.session.add(st)
    db.session.commit()
    return jsonify({"ok": True, "id": st.id, "title": st.title, "done": st.done})


@tasks_bp.route("/api/subtasks/<int:sid>/toggle", methods=["POST"])
@login_required
def api_toggle_subtask(sid):
    st = db.session.get(Subtask, sid)
    if not st:
        return jsonify({"error": "not found"}), 404
    st.done = not st.done
    db.session.commit()
    return jsonify({"ok": True, "done": st.done})


@tasks_bp.route("/api/subtasks/<int:sid>", methods=["DELETE"])
@login_required
def api_delete_subtask(sid):
    st = db.session.get(Subtask, sid)
    if not st:
        return jsonify({"error": "not found"}), 404
    db.session.delete(st)
    db.session.commit()
    return jsonify({"ok": True})
