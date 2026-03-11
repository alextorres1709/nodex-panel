import logging
from datetime import date, timedelta
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, g
from models import db, Payment, Project, Task, Idea, Income, ActivityLog, Client, Invoice, TimeEntry
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
        Task.status.in_(["pendiente", "en_progreso"])).count())
    overdue_tasks = _safe(lambda: Task.query.filter(
        Task.due_date < today,
        Task.status.in_(["pendiente", "en_progreso"])).count())
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

    monthly_income = _safe(lambda: sum(
        i.amount for i in Income.query.filter(
            Income.status == "cobrado",
            db.extract("month", Income.paid_date) == now_month,
            db.extract("year", Income.paid_date) == now_year,
        ).all()
    ))
    monthly_income += _safe(lambda: float(db.session.query(
        db.func.coalesce(db.func.sum(Invoice.total), 0)
    ).filter(
        Invoice.status == "cobrada",
        db.extract("month", Invoice.paid_date) == now_month,
        db.extract("year", Invoice.paid_date) == now_year,
    ).scalar()))

    # ── My tasks (assigned to current user) ──
    my_tasks = _safe(lambda: Task.query.options(joinedload(Task.project)).filter(
        Task.assigned_to == user.id,
        Task.status.in_(["pendiente", "en_progreso"]),
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
    )
