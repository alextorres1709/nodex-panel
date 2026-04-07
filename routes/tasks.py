from datetime import datetime, date, timezone, timedelta
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Task, TaskAssignment, Subtask, User, Project, REMINDER_CHOICES
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

    q = Task.query.options(joinedload(Task.assignees), joinedload(Task.project))
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if assigned:
        q = q.filter(Task.assignees.any(User.id == int(assigned)))
    tasks = q.order_by(Task.kanban_order.asc(), Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    # Group by status for Kanban
    kanban = {
        "pendiente": [t for t in tasks if t.status == "pendiente"],
        "en_progreso": [t for t in tasks if t.status == "en_progreso"],
        "completada": [t for t in tasks if t.status == "completada"],
    }

    # Stats
    all_tasks = Task.query.all()
    total = len(all_tasks)
    pending = sum(1 for t in all_tasks if t.status == "pendiente")
    in_progress = sum(1 for t in all_tasks if t.status == "en_progreso")
    completed = sum(1 for t in all_tasks if t.status == "completada")
    overdue = sum(1 for t in all_tasks if t.safe_due_date and t.safe_due_date < date.today() and t.status != "completada")

    users = User.query.filter_by(active=True).all()
    projects = Project.query.order_by(Project.name).all()

    return render_template("tareas.html", tasks=tasks, kanban=kanban, users=users, projects=projects,
                           sel_status=status, sel_priority=priority, sel_assigned=assigned, view=view,
                           today=date.today(), reminder_choices=REMINDER_CHOICES,
                           stats={"total": total, "pending": pending, "in_progress": in_progress,
                                  "completed": completed, "overdue": overdue})


@tasks_bp.route("/tareas/create", methods=["POST"])
@login_required
def create():
    try:
        dd = request.form.get("due_date", "").strip()
        pid = request.form.get("project_id", "").strip()
        em = request.form.get("estimated_minutes", "").strip()
        assigned_ids = request.form.getlist("assigned_to")
        rm = request.form.get("reminder_minutes", "0").strip()
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            priority=request.form.get("priority", "media"),
            status=request.form.get("status", "pendiente"),
            due_date=datetime.strptime(dd, "%Y-%m-%d").date() if dd else None,
            project_id=int(pid) if pid else None,
            estimated_minutes=int(em) if em else 0,
            recurrence=request.form.get("recurrence", "ninguna"),
            reminder_minutes=int(rm) if rm else 0,
        )
        db.session.add(t)
        db.session.flush()

        # Assignees (multi)
        for uid in assigned_ids:
            uid = uid.strip()
            if uid:
                ta = TaskAssignment(task_id=t.id, user_id=int(uid))
                db.session.add(ta)

        # Subtasks
        sub_titles = request.form.getlist("subtask_title")
        for st in sub_titles:
            st = st.strip()
            if st:
                db.session.add(Subtask(task_id=t.id, title=st))

        log_activity("create", "task", details=f"Nueva tarea: {t.title}")
        db.session.commit()
        from services.sync import push_change
        push_change("tasks", t.id)
        for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
            push_change("task_assignments", ta.id)
        for st in Subtask.query.filter_by(task_id=t.id).all():
            push_change("subtasks", st.id)
        # Notify assigned users about the new task
        from services.notifications import notify
        from services.push import send_push
        from flask import g as _g
        for uid in assigned_ids:
            uid = uid.strip()
            if uid and int(uid) != _g.user.id:
                notify(int(uid), "task", f"Nueva tarea asignada: {t.title}",
                       body=f"Prioridad: {t.priority}" + (f" — Fecha: {t.due_date.strftime('%d/%m/%Y')}" if t.due_date else ""),
                       link="/tareas")
                send_push(int(uid), f"Nueva tarea: {t.title}",
                          body=f"Prioridad: {t.priority}", link="/tareas")
        # Native macOS notification
        try:
            from services.native_notify import send_native_notification
            send_native_notification("NodexAI Panel", f"Tarea creada: {t.title}")
        except Exception:
            pass
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
        t.priority = request.form.get("priority", t.priority)
        t.status = request.form.get("status", t.status)
        dd = request.form.get("due_date", "").strip()
        t.due_date = datetime.strptime(dd, "%Y-%m-%d").date() if dd else None
        pid = request.form.get("project_id", "").strip()
        t.project_id = int(pid) if pid else None
        em = request.form.get("estimated_minutes", "").strip()
        t.estimated_minutes = int(em) if em else 0
        t.recurrence = request.form.get("recurrence", t.recurrence or "ninguna")
        rm = request.form.get("reminder_minutes", "").strip()
        if rm != "":
            t.reminder_minutes = int(rm)

        # Update assignees (replace all)
        assigned_ids = request.form.getlist("assigned_to")
        TaskAssignment.query.filter_by(task_id=t.id).delete()
        for uid in assigned_ids:
            uid = uid.strip()
            if uid:
                db.session.add(TaskAssignment(task_id=t.id, user_id=int(uid)))

        log_activity("update", "task", t.id, f"Editada: {t.title}")
        db.session.commit()
        from services.sync import push_change
        push_change("tasks", t.id)
        for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
            push_change("task_assignments", ta.id)
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
        from services.sync import push_change
        push_change("tasks", t.id)
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/delete/<int:tid>", methods=["POST"])
@login_required
def delete(tid):
    t = db.session.get(Task, tid)
    if t:
        log_activity("delete", "task", t.id, f"Eliminada: {t.title}")
        db.session.delete(t)
        db.session.commit()
        from services.sync import push_change
        push_change("tasks", t.id)
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
    from services.sync import push_change
    push_change("tasks", t.id)
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
    from services.sync import push_change
    push_change("subtasks", st.id)
    return jsonify({"ok": True, "id": st.id, "title": st.title, "done": st.done})


@tasks_bp.route("/api/subtasks/<int:sid>/toggle", methods=["POST"])
@login_required
def api_toggle_subtask(sid):
    st = db.session.get(Subtask, sid)
    if not st:
        return jsonify({"error": "not found"}), 404
    st.done = not st.done
    db.session.commit()
    from services.sync import push_change
    push_change("subtasks", st.id)
    return jsonify({"ok": True, "done": st.done})


@tasks_bp.route("/api/subtasks/<int:sid>", methods=["DELETE"])
@login_required
def api_delete_subtask(sid):
    st = db.session.get(Subtask, sid)
    if not st:
        return jsonify({"error": "not found"}), 404
    db.session.delete(st)
    db.session.commit()
    from services.sync import push_change
    push_change("subtasks", sid)
    return jsonify({"ok": True})


# ═══ TASK REMINDERS ═══

@tasks_bp.route("/api/tasks/<int:tid>/reminder", methods=["POST"])
@login_required
def api_update_reminder(tid):
    """Quick-update reminder interval for a task."""
    t = db.session.get(Task, tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    t.reminder_minutes = int(data.get("reminder_minutes", 0))
    db.session.commit()
    return jsonify({"ok": True, "reminder_minutes": t.reminder_minutes})


@tasks_bp.route("/api/tasks/due-reminders")
@login_required
def api_due_reminders():
    """Return pending/in-progress tasks whose reminder interval has elapsed.
    Marks them as notified so they won't fire again until the next interval.

    The local last_notified_at update is pushed to remote immediately, and the
    whole operation runs under the sync lock so the background sync pull can't
    overwrite the update with stale remote data (Task has no updated_at column,
    so the merge would otherwise treat remote as newer)."""
    from services.sync import push_change_now, sync_locked

    now = datetime.now(timezone.utc)

    with sync_locked():
        tasks = Task.query.filter(
            Task.status.in_(["pendiente", "en_progreso"]),
            Task.reminder_minutes > 0,
        ).all()

        due = []
        for t in tasks:
            last = t.last_notified_at or t.created_at
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last >= timedelta(minutes=t.reminder_minutes):
                due.append({"id": t.id, "title": t.title, "description": t.description or ""})
                t.last_notified_at = now

        if due:
            db.session.commit()
            for d in due:
                push_change_now("tasks", d["id"])

    return jsonify({"due": due})

