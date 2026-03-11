import logging
import calendar as cal
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, Task, Payment, Invoice, Project
from routes.auth import login_required

log = logging.getLogger("calendar")
calendar_bp = Blueprint("calendar", __name__)


def _safe_query(query_fn):
    """Run a query and return empty list on any DB error."""
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

    # Clamp
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    # Build calendar weeks
    first_day = date(year, month, 1)
    _, days_in_month = cal.monthrange(year, month)
    start_weekday = first_day.weekday()  # 0=Monday

    # Previous month fill
    if start_weekday > 0:
        prev_date = first_day - timedelta(days=start_weekday)
    else:
        prev_date = first_day

    # Build 6 weeks of days
    cells = []
    current = prev_date
    for _ in range(42):  # 6 weeks
        cells.append({
            "date": current,
            "day": current.day,
            "current_month": current.month == month,
            "today": current == today,
            "events": [],
        })
        current += timedelta(days=1)

    # Collect events for the visible range
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

    # Map events to cells
    date_to_cell = {c["date"]: c for c in cells}

    for t in tasks:
        if t.due_date and t.due_date in date_to_cell:
            date_to_cell[t.due_date]["events"].append({
                "type": "task", "text": t.title, "link": "/tareas"
            })

    for p in payments:
        if p.next_date and p.next_date in date_to_cell:
            date_to_cell[p.next_date]["events"].append({
                "type": "payment", "text": f"{p.name} ({p.amount}€)", "link": "/pagos"
            })

    for i in invoices:
        if i.due_date and i.due_date in date_to_cell:
            date_to_cell[i.due_date]["events"].append({
                "type": "invoice", "text": f"Factura {i.number}", "link": "/facturas"
            })

    for p in projects:
        if p.deadline and p.deadline in date_to_cell:
            date_to_cell[p.deadline]["events"].append({
                "type": "deadline", "text": f"Deadline: {p.name}", "link": "/proyectos"
            })

    # Nav months
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_names = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    # Projects for quick-task modal
    active_projects = Project.query.filter_by(status="activo").order_by(Project.name).all()

    return render_template(
        "calendario.html",
        cells=cells, year=year, month=month,
        month_name=month_names[month],
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        active_projects=active_projects,
    )


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
