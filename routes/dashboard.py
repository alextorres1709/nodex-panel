import logging
from datetime import date, datetime, timedelta
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, g
from models import db, Payment, Project, Task, TaskAssignment, Idea, Income, ActivityLog, Client, Invoice, TimeEntry, Objective
from routes.auth import login_required

log = logging.getLogger("dashboard")
dashboard_bp = Blueprint("dashboard", __name__)


def _safe(fn, default=0):
    try:
        return fn()
    except Exception as e:
        log.warning(f"Dashboard query failed: {e}")
        return default


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    today = date.today()
    now_month = today.month
    now_year = today.year
    user = g.user

    # ── Core counts ──
    active_projects = _safe(lambda: Project.query.filter_by(status="activo").count())
    pending_tasks = _safe(lambda: Task.query.filter(
        Task.status.in_(["pendiente", "en_progreso", "en_espera"])).count())
    overdue_tasks = _safe(lambda: Task.query.filter(
        Task.due_date < today,
        Task.status.in_(["pendiente", "en_progreso", "en_espera"])).count())
    total_tasks = _safe(lambda: Task.query.count())
    completed_tasks = _safe(lambda: Task.query.filter_by(status="completada").count())
    new_ideas = _safe(lambda: Idea.query.filter_by(status="nueva").count())

    # ── Financials ──
    active_payments = _safe(lambda: Payment.query.filter_by(status="activo").all(), [])
    monthly_cost = sum(
        p.amount if p.frequency == "mensual"
        else p.amount / 12 if p.frequency == "anual"
        else 0
        for p in active_payments
    )

    monthly_income = _safe(lambda: float(db.session.query(
        db.func.coalesce(db.func.sum(Income.amount), 0)
    ).filter(
        Income.status == "cobrado",
        db.extract("month", Income.paid_date) == now_month,
        db.extract("year", Income.paid_date) == now_year,
    ).scalar()))
    monthly_income += _safe(lambda: float(db.session.query(
        db.func.coalesce(db.func.sum(Invoice.total), 0)
    ).filter(
        Invoice.status == "cobrada",
        db.extract("month", Invoice.paid_date) == now_month,
        db.extract("year", Invoice.paid_date) == now_year,
    ).scalar()))

    # ── My tasks (assigned to current user via legacy field OR task_assignments) ──
    assigned_via_m2m = db.session.query(TaskAssignment.task_id).filter(
        TaskAssignment.user_id == user.id
    ).subquery()
    my_tasks = _safe(lambda: Task.query.options(joinedload(Task.project)).filter(
        db.or_(Task.assigned_to == user.id, Task.id.in_(assigned_via_m2m)),
        Task.status.in_(["pendiente", "en_progreso", "en_espera"]),
    ).order_by(
        Task.due_date.asc().nullslast(),
        Task.priority.desc(),
    ).limit(10).all(), [])

    # ── Active projects with progress ──
    active_project_list = _safe(lambda: Project.query.filter_by(status="activo")
        .order_by(Project.progress.desc()).limit(6).all(), [])

    # ── Upcoming payments (next 30 days) ──
    month_ahead = today + timedelta(days=30)
    upcoming_payments = _safe(lambda: Payment.query.filter(
        Payment.next_date.isnot(None),
        Payment.next_date <= month_ahead,
        Payment.next_date >= today,
        Payment.status == "activo",
    ).order_by(Payment.next_date.asc()).limit(5).all(), [])

    # ── Recent activity ──
    recent_activity = _safe(lambda: ActivityLog.query.options(
        joinedload(ActivityLog.user)
    ).order_by(ActivityLog.created_at.desc()).limit(8).all(), [])

    # ── Gastos por categoria (chart) ──
    cost_chart = _safe(lambda: db.session.query(
        Payment.category, db.func.sum(Payment.amount)
    ).filter_by(status="activo", frequency="mensual")
    .group_by(Payment.category).all(), [])
    cost_labels = [r[0] or "otro" for r in cost_chart]
    cost_values = [float(r[1] or 0) for r in cost_chart]

    # ── 6-month Income vs Expenses chart ──
    # Build the 6 (year, month) pairs first
    import calendar as cal_mod
    month_labels = []
    month_keys = []
    for i in range(5, -1, -1):
        m = now_month - i
        y = now_year
        while m <= 0:
            m += 12
            y -= 1
        month_labels.append(cal_mod.month_abbr[m])
        month_keys.append((y, m))

    # Range covering the earliest of the 6 months → today (drops unrelated rows)
    earliest_y, earliest_m = month_keys[0]
    period_start = date(earliest_y, earliest_m, 1)

    # Two grouped queries instead of 12 scalar queries
    income_rows = _safe(lambda: db.session.query(
        db.extract("year", Income.paid_date),
        db.extract("month", Income.paid_date),
        db.func.coalesce(db.func.sum(Income.amount), 0),
    ).filter(
        Income.status == "cobrado",
        Income.paid_date >= period_start,
    ).group_by(
        db.extract("year", Income.paid_date),
        db.extract("month", Income.paid_date),
    ).all(), [])
    invoice_rows = _safe(lambda: db.session.query(
        db.extract("year", Invoice.paid_date),
        db.extract("month", Invoice.paid_date),
        db.func.coalesce(db.func.sum(Invoice.total), 0),
    ).filter(
        Invoice.status == "cobrada",
        Invoice.paid_date >= period_start,
    ).group_by(
        db.extract("year", Invoice.paid_date),
        db.extract("month", Invoice.paid_date),
    ).all(), [])

    income_by_ym = {}
    for y, m, total in income_rows:
        income_by_ym[(int(y), int(m))] = income_by_ym.get((int(y), int(m)), 0) + float(total or 0)
    for y, m, total in invoice_rows:
        income_by_ym[(int(y), int(m))] = income_by_ym.get((int(y), int(m)), 0) + float(total or 0)

    income_6m = [income_by_ym.get(k, 0) for k in month_keys]
    expense_6m = [monthly_cost] * 6  # flat monthly cost estimate

    # ── Personal stats (this week) ──
    week_start = today - timedelta(days=today.weekday())
    week_hours = _safe(lambda: (db.session.query(
        db.func.coalesce(db.func.sum(TimeEntry.minutes), 0)
    ).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= week_start,
    ).scalar() or 0) / 60)
    week_tasks = _safe(lambda: Task.query.filter(
        Task.assigned_to == user.id,
        Task.status == "completada",
        Task.created_at >= datetime.combine(week_start, datetime.min.time()),
    ).count())
    week_revenue = _safe(lambda: float(db.session.query(
        db.func.coalesce(db.func.sum(Invoice.total), 0)
    ).filter(
        Invoice.status == "cobrada",
        Invoice.paid_date >= week_start,
    ).scalar()))

    # ── Revenue goal (monthly, default 5000€) ──
    revenue_goal = 5000
    revenue_pct = min(100, int((monthly_income / revenue_goal) * 100)) if revenue_goal > 0 else 0

    # ── Extra stats for dashboard ──
    total_clients = _safe(lambda: Client.query.count())
    pending_invoices = _safe(lambda: Invoice.query.filter(
        Invoice.status.in_(["borrador", "enviada"])
    ).count())
    balance = monthly_income - monthly_cost

    # ── Tareas atrasadas concretas (top 5) — para alerta de acción rápida ──
    overdue_task_list = _safe(lambda: Task.query.options(joinedload(Task.project)).filter(
        Task.due_date < today,
        Task.status.in_(["pendiente", "en_progreso", "en_espera"]),
    ).order_by(Task.due_date.asc()).limit(5).all(), [])

    # ── Top facturas pendientes de cobro (impagadas / vencidas) ──
    top_pending_invoices = _safe(lambda: Invoice.query.options(
        joinedload(Invoice.client)
    ).filter(
        Invoice.status.in_(["enviada", "vencida"])
    ).order_by(Invoice.due_date.asc().nullslast(), Invoice.created_at.desc()).limit(5).all(), [])
    pending_invoices_total = _safe(lambda: float(db.session.query(
        db.func.coalesce(db.func.sum(Invoice.total), 0)
    ).filter(Invoice.status.in_(["enviada", "vencida"])).scalar()))

    # ── Objetivos activos del usuario (top 4 por progreso ascendente) ──
    my_objectives = _safe(lambda: Objective.query.filter(
        Objective.assigned_to == user.id,
        Objective.status.in_(["nuevo", "en_progreso"]),
    ).order_by(Objective.progress.asc(), Objective.target_date.asc().nullslast()).limit(4).all(), [])

    return render_template(
        "dashboard.html",
        today=today,
        # Counts
        active_projects=active_projects,
        pending_tasks=pending_tasks,
        overdue_tasks=overdue_tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        new_ideas=new_ideas,
        # Financial
        monthly_cost=monthly_cost,
        monthly_income=monthly_income,
        # Lists
        my_tasks=my_tasks,
        active_project_list=active_project_list,
        upcoming_payments=upcoming_payments,
        recent_activity=recent_activity,
        # Chart
        cost_labels=cost_labels,
        cost_values=cost_values,
        # NEW: 6-month chart
        month_labels=month_labels,
        income_6m=income_6m,
        expense_6m=expense_6m,
        # Personal stats
        week_hours=round(week_hours, 1),
        week_tasks=week_tasks,
        week_revenue=week_revenue,
        # NEW: Revenue goal
        revenue_goal=revenue_goal,
        revenue_pct=revenue_pct,
        # Extra stats
        total_clients=total_clients,
        pending_invoices=pending_invoices,
        balance=balance,
        # NEW v4.5.1: action items
        overdue_task_list=overdue_task_list,
        top_pending_invoices=top_pending_invoices,
        pending_invoices_total=pending_invoices_total,
        my_objectives=my_objectives,
    )
