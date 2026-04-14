import logging
import calendar as cal
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from models import db, Task, Payment, Invoice, Project, CalendarEvent, User
from routes.auth import login_required
from services.sync import push_change_now, sync_locked

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

    prev_date = first_day - timedelta(days=start_weekday) if start_weekday > 0 else first_day

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

    # Google Calendar connection status for the current user
    from services import gcal as gcal_svc
    gcal_configured = gcal_svc.is_configured()
    gcal_connected = gcal_svc.is_connected(g.user.id) if gcal_configured else False

    return render_template(
        "calendario.html",
        cells=cells, year=year, month=month,
        month_name=month_names[month],
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        active_projects=active_projects,
        users=users,
        today=today,
        gcal_configured=gcal_configured,
        gcal_connected=gcal_connected,
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

    # Auto-sync to Google Calendar
    _gcal_push(ev, g.user.id)

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

    # Auto-sync to Google Calendar
    _gcal_push(ev, g.user.id)

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
    gcal_id = ev.gcal_event_id

    from services.activity import log_activity
    with sync_locked():
        log_activity("elimino", "evento", eid, title)
        db.session.delete(ev)
        db.session.commit()
        push_change_now("calendar_events", eid)

    # Remove from Google Calendar
    if gcal_id:
        try:
            from services import gcal as gcal_svc
            gcal_svc.delete_event(gcal_id, g.user.id)
        except Exception as e:
            log.warning(f"GCal delete skipped: {e}")

    return jsonify({"ok": True})


@calendar_bp.route("/api/calendar/event/<int:eid>")
@login_required
def get_event(eid):
    ev = db.session.get(CalendarEvent, eid)
    if not ev:
        return jsonify({"error": "No encontrado"}), 404
    return jsonify({"event": _event_dict(ev)})


# ═══ GOOGLE CALENDAR OAUTH ROUTES ═══

@calendar_bp.route("/calendario/gcal/auth")
@login_required
def gcal_auth():
    """Redirect user to Google OAuth2 consent screen."""
    from services import gcal as gcal_svc
    if not gcal_svc.is_configured():
        flash("Google Calendar no está configurado. Añade GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET al .env", "error")
        return redirect(url_for("calendar.index"))
    auth_url = gcal_svc.get_auth_url(state=str(g.user.id))
    return redirect(auth_url)


@calendar_bp.route("/calendario/gcal/callback")
@login_required
def gcal_callback():
    """Handle Google OAuth2 callback, exchange code for tokens."""
    from services import gcal as gcal_svc

    error = request.args.get("error")
    if error:
        flash(f"Google Calendar: acceso denegado ({error})", "error")
        return redirect(url_for("calendar.index"))

    code = request.args.get("code")
    if not code:
        flash("No se recibió código de autorización de Google", "error")
        return redirect(url_for("calendar.index"))

    try:
        # Pass redirect_uri derived from the current request so it matches
        # the one used in gcal_auth() — critical for the packaged app which
        # runs on a random port, not necessarily 5001.
        from flask import request as _req
        callback_uri = _req.host_url.rstrip("/") + "/calendario/gcal/callback"
        token_dict = gcal_svc.exchange_code(code, redirect_uri=callback_uri)
        gcal_svc._save_token(g.user.id, token_dict)
        flash("✅ Google Calendar conectado correctamente", "success")

        # Bulk-sync existing panel events immediately
        synced, failed = gcal_svc.bulk_sync_user(g.user.id)
        if synced:
            flash(f"Se sincronizaron {synced} evento(s) existentes a Google Calendar", "success")
    except Exception as e:
        log.error(f"GCal OAuth callback error: {e}")
        flash(f"Error al conectar Google Calendar: {e}", "error")

    return redirect(url_for("calendar.index"))


@calendar_bp.route("/calendario/gcal/disconnect", methods=["POST"])
@login_required
def gcal_disconnect():
    """Remove stored Google Calendar OAuth token."""
    from services import gcal as gcal_svc
    gcal_svc.disconnect(g.user.id)
    flash("Google Calendar desconectado", "success")
    return redirect(url_for("calendar.index"))


@calendar_bp.route("/calendario/gcal/sync", methods=["POST"])
@login_required
def gcal_sync():
    """Manually push all events that don't have a gcal_event_id yet."""
    from services import gcal as gcal_svc
    if not gcal_svc.is_connected(g.user.id):
        return jsonify({"error": "No conectado a Google Calendar"}), 400
    synced, failed = gcal_svc.bulk_sync_user(g.user.id)
    return jsonify({"ok": True, "synced": synced, "failed": failed})


# ═══ QUICK TASK (legacy) ═══

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


# ═══ HELPERS ═══

def _gcal_push(ev, user_id: int):
    """Push event to Google Calendar (fire-and-forget). Saves gcal_event_id."""
    try:
        from services import gcal as gcal_svc
        if gcal_svc.is_configured() and gcal_svc.is_connected(user_id):
            gcal_id = gcal_svc.push_event(ev, user_id)
            if gcal_id and gcal_id != ev.gcal_event_id:
                ev.gcal_event_id = gcal_id
                db.session.commit()
    except Exception as e:
        log.warning(f"GCal push skipped: {e}")


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
        "gcal_event_id": ev.gcal_event_id,
        "creator_name": ev.creator.name if ev.creator else None,
        "assignee_name": ev.assignee.name if ev.assignee else None,
    }
