import re
from datetime import datetime, date, timezone, timedelta
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from models import db, Task, TaskAssignment, TaskComment, Subtask, User, Project, REMINDER_CHOICES
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

tasks_bp = Blueprint("tasks", __name__)


def _gcal_push_item(item_type, item):
    try:
        from services import gcal as gcal_svc
        from flask import g
        if item_type == "task":
            has_assignees = hasattr(item, "assignees") and item.assignees
            if has_assignees or getattr(item, "assigned_to", None):
                assignee_ids = [a.id for a in item.assignees] if has_assignees else [item.assigned_to]
                for uid in assignee_ids:
                    if gcal_svc.is_configured() and gcal_svc.is_connected(uid):
                        gcal_svc.push_item(item_type, item, uid)
                        if item.due_date:
                            gcal_svc.push_item("task_event", item, uid)
            else:
                # Tarea sin asignar: sincroniza a todos los usuarios activos
                from models import User
                for u in User.query.filter_by(active=True).all():
                    if gcal_svc.is_configured() and gcal_svc.is_connected(u.id):
                        gcal_svc.push_item(item_type, item, u.id)
                        if item.due_date:
                            gcal_svc.push_item("task_event", item, u.id)
        else:
            # Fallback or other items to current user
            if gcal_svc.is_configured() and getattr(g, "user", None) and gcal_svc.is_connected(g.user.id):
                gcal_svc.push_item(item_type, item, g.user.id)
    except Exception as e:
        pass


def _gcal_delete_item(item_type, item_id, item=None):
    try:
        from services import gcal as gcal_svc
        from flask import g
        if item_type == "task" and item:
            has_assignees = hasattr(item, "assignees") and item.assignees
            if has_assignees or getattr(item, "assigned_to", None):
                assignee_ids = [a.id for a in item.assignees] if has_assignees else [item.assigned_to]
                for uid in assignee_ids:
                    if gcal_svc.is_configured() and gcal_svc.is_connected(uid):
                        gcal_svc.delete_item_event(item_type, item_id, uid)
                        gcal_svc.delete_item_event("task_event", item_id, uid)
            else:
                from models import User
                for u in User.query.filter_by(active=True).all():
                    if gcal_svc.is_configured() and gcal_svc.is_connected(u.id):
                        gcal_svc.delete_item_event(item_type, item_id, u.id)
                        gcal_svc.delete_item_event("task_event", item_id, u.id)
        else:
            if gcal_svc.is_configured() and getattr(g, "user", None) and gcal_svc.is_connected(g.user.id):
                gcal_svc.delete_item_event(item_type, item_id, g.user.id)
    except Exception as e:
        pass


@tasks_bp.route("/tareas")
@login_required
def index():
    view = request.args.get("view", "kanban")
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    assigned = request.args.get("assigned_to", "")

    q = Task.query.options(joinedload(Task.assignees), joinedload(Task.project), joinedload(Task.company))
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if assigned:
        q = q.filter(Task.assignees.any(User.id == int(assigned)))
    tasks = q.order_by(Task.kanban_order.asc(), Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    # For list view: re-sort by priority (alta first), then nearest due_date, then newest
    if view == "list":
        _PRIO_RANK = {"alta": 0, "media": 1, "baja": 2}
        _today = date.today()
        def _key(t):
            prio = _PRIO_RANK.get(t.priority or "media", 1)
            d = t.safe_due_date
            days = (d - _today).days if d else 9999
            ts = -(t.created_at.timestamp() if t.created_at else 0)
            return (prio, days, ts)
        tasks = sorted(tasks, key=_key)

    # Group by status for Kanban
    kanban = {
        "pendiente": [t for t in tasks if t.status == "pendiente"],
        "en_progreso": [t for t in tasks if t.status == "en_progreso"],
        "completada": [t for t in tasks if t.status == "completada"],
    }

    # Stats — computed via lightweight COUNT queries (no second full load)
    from sqlalchemy import func, and_
    status_counts = dict(
        db.session.query(Task.status, func.count(Task.id)).group_by(Task.status).all()
    )
    total = sum(status_counts.values())
    pending = status_counts.get("pendiente", 0)
    in_progress = status_counts.get("en_progreso", 0)
    completed = status_counts.get("completada", 0)
    overdue = db.session.query(func.count(Task.id)).filter(
        and_(Task.due_date < date.today(), Task.status != "completada")
    ).scalar() or 0

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
        _gcal_push_item("task", t)
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
        _gcal_push_item("task", t)
        from services.sync import push_change
        push_change("tasks", t.id)
        for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
            push_change("task_assignments", ta.id)
        flash("Tarea actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("tasks.index"))


def _maybe_clone_recurring(task):
    """Si la tarea tiene recurrencia, genera la siguiente instancia.
    Devuelve la nueva Task creada o None."""
    rec = (task.recurrence or "ninguna").lower()
    if rec in ("", "ninguna", "none"):
        return None

    base = task.due_date or date.today()
    if rec == "diaria":
        next_due = base + timedelta(days=1)
    elif rec == "semanal":
        next_due = base + timedelta(days=7)
    elif rec == "mensual":
        # +30 días aproximado (sin dependencias extra)
        next_due = base + timedelta(days=30)
    elif rec == "anual":
        try:
            next_due = base.replace(year=base.year + 1)
        except ValueError:
            next_due = base + timedelta(days=365)
    else:
        return None

    clone = Task(
        title=task.title,
        description=task.description,
        priority=task.priority,
        status="pendiente",
        project_id=task.project_id,
        company_id=task.company_id,
        due_date=next_due,
        estimated_minutes=task.estimated_minutes,
        recurrence=task.recurrence,
        reminder_minutes=task.reminder_minutes,
    )
    db.session.add(clone)
    db.session.flush()
    # Replicar asignaciones
    for ta in TaskAssignment.query.filter_by(task_id=task.id).all():
        db.session.add(TaskAssignment(task_id=clone.id, user_id=ta.user_id))
    return clone


@tasks_bp.route("/tareas/toggle/<int:tid>", methods=["POST"])
@login_required
def toggle(tid):
    t = db.session.get(Task, tid)
    if t:
        was_complete = t.status == "completada"
        t.status = "completada" if not was_complete else "pendiente"
        log_activity("update", "task", t.id, f"{'Completada' if t.status == 'completada' else 'Reabierta'}: {t.title}")

        # Si se acaba de completar y es recurrente, generar la siguiente
        clone = None
        if not was_complete and t.status == "completada":
            clone = _maybe_clone_recurring(t)

        db.session.commit()
        # Completed tasks leave GCal; pending/in-progress get (re)synced
        if t.status == "completada":
            _gcal_delete_item("task", t.id, item=t)
        else:
            _gcal_push_item("task", t)
        if clone:
            _gcal_push_item("task", clone)
        from services.sync import push_change
        push_change("tasks", t.id)
        if clone:
            push_change("tasks", clone.id)
            for ta in TaskAssignment.query.filter_by(task_id=clone.id).all():
                push_change("task_assignments", ta.id)
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/duplicate/<int:tid>", methods=["POST"])
@login_required
def duplicate(tid):
    t = db.session.get(Task, tid)
    if not t:
        flash("Tarea no encontrada", "error")
        return redirect(url_for("tasks.index"))
    clone = Task(
        title=f"{t.title} (copia)",
        description=t.description,
        priority=t.priority,
        status="pendiente",
        project_id=t.project_id,
        company_id=t.company_id,
        due_date=t.due_date,
        estimated_minutes=t.estimated_minutes,
        recurrence=t.recurrence,
        reminder_minutes=t.reminder_minutes,
    )
    db.session.add(clone)
    db.session.flush()
    for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
        db.session.add(TaskAssignment(task_id=clone.id, user_id=ta.user_id))
    log_activity("create", "task", clone.id, f"Duplicada de #{t.id}: {t.title}")
    db.session.commit()
    push_change("tasks", clone.id)
    for ta in TaskAssignment.query.filter_by(task_id=clone.id).all():
        push_change("task_assignments", ta.id)
    flash("Tarea duplicada", "success")
    return redirect(url_for("tasks.index"))


@tasks_bp.route("/tareas/delete/<int:tid>", methods=["POST"])
@login_required
def delete(tid):
    t = db.session.get(Task, tid)
    if t:
        tid_val = t.id
        _gcal_delete_item("task", tid_val, item=t)
        with sync_locked():
            log_activity("delete", "task", t.id, f"Eliminada: {t.title}")
            db.session.delete(t)
            db.session.commit()
            push_change_now("tasks", tid_val)
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
    prev_status = t.status
    if new_status in ("pendiente", "en_progreso", "completada"):
        t.status = new_status
    t.kanban_order = new_order
    log_activity("update", "task", t.id, f"Movida a {t.status}: {t.title}")

    # Si se completó vía drag&drop y es recurrente, clonar la siguiente
    clone = None
    if prev_status != "completada" and t.status == "completada":
        clone = _maybe_clone_recurring(t)

    db.session.commit()
    from services.sync import push_change
    push_change("tasks", t.id)
    if clone:
        push_change("tasks", clone.id)
        for ta in TaskAssignment.query.filter_by(task_id=clone.id).all():
            push_change("task_assignments", ta.id)
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
    with sync_locked():
        db.session.delete(st)
        db.session.commit()
        push_change_now("subtasks", sid)
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


# ─────────────────────────────────────────────────────────────────────────────
# Comentarios + menciones (@usuario)
# ─────────────────────────────────────────────────────────────────────────────

_MENTION_RE = re.compile(r"@([a-zA-Z0-9_\-]+)")


def _parse_mentions(text):
    """Devuelve lista de User encontrados a partir de @nombre dentro de text."""
    if not text:
        return []
    raw = set(m.lower() for m in _MENTION_RE.findall(text))
    if not raw:
        return []
    users = User.query.filter(User.active.is_(True)).all()
    out = []
    for u in users:
        first = (u.name or "").split()[0].lower() if u.name else ""
        if first and first in raw:
            out.append(u)
    return out


@tasks_bp.route("/api/tasks/<int:task_id>/comments")
@login_required
def api_task_comments(task_id):
    Task.query.get_or_404(task_id)
    rows = TaskComment.query.filter_by(task_id=task_id).order_by(TaskComment.created_at.asc()).all()
    return jsonify({"comments": [{
        "id": c.id,
        "content": c.content,
        "author": c.author.name if c.author else "—",
        "author_id": c.author_id,
        "created_at": (c.created_at.isoformat() if c.created_at else None),
    } for c in rows]})


@tasks_bp.route("/api/tasks/<int:task_id>/comments", methods=["POST"])
@login_required
def api_task_comment_create(task_id):
    from flask import g
    task = Task.query.get_or_404(task_id)
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "vacío"}), 400

    user = g.get("user")
    c = TaskComment(task_id=task.id, author_id=(user.id if user else None), content=content)
    db.session.add(c)
    db.session.commit()
    push_change("task_comments", c.id)

    # Notificar a los mencionados (notify ya envía FCM internamente)
    try:
        from services.notifications import notify
        for u in _parse_mentions(content):
            if user and u.id == user.id:
                continue
            notify(
                user_id=u.id,
                type="mention",
                title=f"Te mencionaron en «{task.title}»",
                body=content[:140],
                link=f"/tareas#task-{task.id}",
            )
    except Exception:
        pass

    log_activity("task_comment_create", "task", task.id, f"Comentario en {task.title}")
    return jsonify({"ok": True, "id": c.id})


@tasks_bp.route("/api/tasks/<int:task_id>/comments/<int:comment_id>", methods=["DELETE"])
@login_required
def api_task_comment_delete(task_id, comment_id):
    from flask import g
    c = TaskComment.query.filter_by(id=comment_id, task_id=task_id).first_or_404()
    user = g.get("user")
    # Solo autor o admin pueden borrar
    if user and c.author_id and c.author_id != user.id and user.role != "admin":
        return jsonify({"error": "forbidden"}), 403
    db.session.delete(c)
    db.session.commit()
    push_change("task_comments", comment_id)
    return jsonify({"ok": True})

