import logging
import calendar as cal
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from models import db, Task, Payment, Invoice, Project, CalendarEvent, User
from routes.auth import login_required

log = logging.getLogger("calendar")
calendar_bp = Blueprint("calendar", __name__)


def _safe_query(query_fn):
    try:
        return query_fn()
    except Exception as e:
        log.warning(f"Calendar query failed: {e}")
        return []


@calendar_bp.route("/calendario")
@login_required
def index():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    first_day = date(year, month, 1)
    _, days_in_month = cal.monthrange(year, month)
    start_weekday = first_day.weekday()

    if start_weekday > 0:
        prev_date = first_day - timedelta(days=start_weekday)
    else:
        prev_date = first_day

    cells = []
    current = prev_date
    for _ in range(42):
        cells.append({
            "date": current,
            "day": current.day,
            "current_month": current.month == month,
            "today": current == today,
            "events": [],
        })
        current += timedelta(days=1)

    range_start = cells[0]["date"]
    range_end = cells[-1]["date"]

    tasks = _safe_query(lambda: Task.query.filter(
        Task.due_date.isnot(None),
        Task.due_date >= range_start,
        Task.due_date <= range_end,
        Task.status.in_(["pendiente", "en_progreso"]),
    ).all())

    payments = _safe_query(lambda: Payment.query.filter(
        Payment.next_date.isnot(None),
        Payment.next_date >= range_start,
        Payment.next_date <= range_end,
        Payment.status == "activo",
    ).all())

    invoices = _safe_query(lambda: Invoice.query.filter(
        Invoice.due_date.isnot(None),
        Invoice.due_date >= range_start,
        Invoice.due_date <= range_end,
        Invoice.status.in_(["enviada", "vencida"]),
    ).all())

    projects = _safe_query(lambda: Project.query.filter(
        Project.deadline.isnot(None),
        Project.deadline >= range_start,
        Project.deadline <= range_end,
        Project.status == "activo",
    ).all())

    events = _safe_query(lambda: CalendarEvent.query.filter(
        CalendarEvent.date >= range_start,
        CalendarEvent.date <= range_end,
    ).all())

    date_to_cell = {c["date"]: c for c in cells}

    for t in tasks:
        if t.due_date and t.due_date in date_to_cell:
            date_to_cell[t.due_date]["events"].append({
                "type": "task", "text": t.title, "link": "/tareas",
                "time": None, "id": None,
            })

    for p in payments:
        if p.next_date and p.next_date in date_to_cell:
            date_to_cell[p.next_date]["events"].append({
                "type": "payment", "text": f"{p.name} ({p.amount}\u20ac)", "link": "/pagos",
                "time": None, "id": None,
            })

    for i in invoices:
        if i.due_date and i.due_date in date_to_cell:
            date_to_cell[i.due_date]["events"].append({
                "type": "invoice", "text": f"Factura {i.number}", "link": "/facturas",
                "time": None, "id": None,
            })

    for p in projects:
        if p.deadline and p.deadline in date_to_cell:
            date_to_cell[p.deadline]["events"].append({
                "type": "deadline", "text": f"Deadline: {p.name}", "link": "/proyectos",
                "time": None, "id": None,
            })

    for ev in events:
        if ev.date and ev.date in date_to_cell:
            date_to_cell[ev.date]["events"].append({
                "type": ev.event_type,
                "text": ev.title,
                "time": ev.start_time,
                "id": ev.id,
                "link": None,
            })

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_names = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    active_projects = _safe_query(
        lambda: Project.query.filter_by(status="activo").order_by(Project.name).all()
    )
    users = _safe_query(lambda: User.query.filter_by(active=True).all())

    return render_template(
        "calendario.html",
        cells=cells, year=year, month=month,
        month_name=month_names[month],
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        active_projects=active_projects,
        users=users,
        today=today,
    )


# ═══ CRUD — CalendarEvent (AJAX) ═══

@calendar_bp.route("/calendario/event", methods=["POST"])
@login_required
def create_event():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "El titulo es obligatorio"}), 400

    try:
        ev_date = date.fromisoformat(data.get("date", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "Fecha invalida"}), 400

    ev = CalendarEvent(
        title=title,
        description=data.get("description", ""),
        event_type=data.get("event_type", "evento"),
        date=ev_date,
        start_time=data.get("start_time") or None,
        end_time=data.get("end_time") or None,
        location=data.get("location", ""),
        all_day=bool(data.get("all_day", False)),
        created_by=g.user.id,
        assigned_to=int(data["assigned_to"]) if data.get("assigned_to") else None,
    )
    db.session.add(ev)
    db.session.commit()

    from services.activity import log_activity
    log_activity("creo", "evento", ev.id, ev.title)
    try:
        from services.sync import push_change
        push_change("calendar_events", ev.id)
    except Exception:
        pass

    return jsonify({"ok": True, "event": _event_dict(ev)}), 201


@calendar_bp.route("/calendario/event/<int:eid>", methods=["PUT"])
@login_required
def update_event(eid):
    ev = db.session.get(CalendarEvent, eid)
    if not ev:
        return jsonify({"error": "No encontrado"}), 404

    data = request.get_json(force=True)
    if "title" in data:
        ev.title = (data["title"] or "").strip()
    if "description" in data:
        ev.description = data["description"]
    if "event_type" in data:
        ev.event_type = data["event_type"]
    if "date" in data:
        try:
            ev.date = date.fromisoformat(data["date"])
        except (ValueError, TypeError):
            pass
    if "start_time" in data:
        ev.start_time = data["start_time"] or None
    if "end_time" in data:
        ev.end_time = data["end_time"] or None
    if "location" in data:
        ev.location = data["location"]
    if "all_day" in data:
        ev.all_day = bool(data["all_day"])
    if "assigned_to" in data:
        ev.assigned_to = int(data["assigned_to"]) if data["assigned_to"] else None

    db.session.commit()

    from services.activity import log_activity
    log_activity("edito", "evento", ev.id, ev.title)
    try:
        from services.sync import push_change
        push_change("calendar_events", ev.id)
    except Exception:
        pass

    return jsonify({"ok": True, "event": _event_dict(ev)})


@calendar_bp.route("/calendario/event/<int:eid>", methods=["DELETE"])
@login_required
def delete_event(eid):
    ev = db.session.get(CalendarEvent, eid)
    if not ev:
        return jsonify({"error": "No encontrado"}), 404

    title = ev.title
    db.session.delete(ev)
    db.session.commit()

    from services.activity import log_activity
    log_activity("elimino", "evento", eid, title)
    try:
        from services.sync import push_change
        push_change("calendar_events", eid)
    except Exception:
        pass

    return jsonify({"ok": True})


@calendar_bp.route("/api/calendar/event/<int:eid>")
@login_required
def get_event(eid):
    ev = db.session.get(CalendarEvent, eid)
    if not ev:
        return jsonify({"error": "No encontrado"}), 404
    return jsonify({"event": _event_dict(ev)})


# Keep quick-task for backwards compat
@calendar_bp.route("/calendario/quick-task", methods=["POST"])
@login_required
def quick_task():
    title = request.form.get("title", "").strip()
    due_date_str = request.form.get("due_date", "")
    priority = request.form.get("priority", "media")
    project_id = request.form.get("project_id") or None

    if not title:
        flash("El titulo es obligatorio", "error")
        return redirect(url_for("calendar.index"))

    try:
        due_date = date.fromisoformat(due_date_str)
    except (ValueError, TypeError):
        due_date = None

    task = Task(
        title=title,
        priority=priority,
        status="pendiente",
        due_date=due_date,
        assigned_to=g.user.id,
        project_id=int(project_id) if project_id else None,
    )
    db.session.add(task)
    db.session.commit()

    from services.activity import log_activity
    log_activity("creo", "tarea", task.id, task.title)

    flash(f"Tarea '{title}' creada", "success")
    if due_date:
        return redirect(url_for("calendar.index", year=due_date.year, month=due_date.month))
    return redirect(url_for("calendar.index"))


def _event_dict(ev):
    return {
        "id": ev.id,
        "title": ev.title,
        "description": ev.description or "",
        "event_type": ev.event_type,
        "date": ev.date.isoformat() if ev.date else None,
        "start_time": ev.start_time,
        "end_time": ev.end_time,
        "location": ev.location or "",
        "all_day": ev.all_day,
        "created_by": ev.created_by,
        "assigned_to": ev.assigned_to,
        "creator_name": ev.creator.name if ev.creator else None,
        "assignee_name": ev.assignee.name if ev.assignee else None,
    }
