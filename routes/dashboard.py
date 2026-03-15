import logging
from datetime import date, datetime, timedelta
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

    # ── 6-month Income vs Expenses chart ──
    import calendar as cal_mod
    month_labels = []
    income_6m = []
    expense_6m = []
    for i in range(5, -1, -1):
        m = now_month - i
        y = now_year
        while m <= 0:
            m += 12
            y -= 1
        month_labels.append(cal_mod.month_abbr[m])
        # Income for month
        inc = _safe(lambda m=m, y=y: sum(
            x.amount for x in Income.query.filter(
                Income.status == "cobrado",
                db.extract("month", Income.paid_date) == m,
                db.extract("year", Income.paid_date) == y,
            ).all()
        ))
        inc += _safe(lambda m=m, y=y: float(db.session.query(
            db.func.coalesce(db.func.sum(Invoice.total), 0)
        ).filter(
            Invoice.status == "cobrada",
            db.extract("month", Invoice.paid_date) == m,
            db.extract("year", Invoice.paid_date) == y,
        ).scalar()))
        income_6m.append(inc)
        expense_6m.append(monthly_cost)  # flat monthly cost estimate

    # ── Activity heatmap (last 12 weeks = 84 days) ──
    heatmap_data = []
    for i in range(83, -1, -1):
        d = today - timedelta(days=i)
        count = _safe(lambda d=d: ActivityLog.query.filter(
            db.func.date(ActivityLog.created_at) == d
        ).count())
        level = 0 if count == 0 else 1 if count <= 2 else 2 if count <= 5 else 3 if count <= 10 else 4
        heatmap_data.append({"date": d.strftime("%d/%m"), "level": level, "count": count})

    # ── Personal stats (this week) ──
    week_start = today - timedelta(days=today.weekday())
    week_hours = _safe(lambda: sum(
        e.minutes for e in TimeEntry.query.filter(
            TimeEntry.user_id == user.id,
            TimeEntry.date >= week_start,
        ).all()
    ) / 60)
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
        # NEW: Heatmap
        heatmap_data=heatmap_data,
        # NEW: Personal stats
        week_hours=round(week_hours, 1),
        week_tasks=week_tasks,
        week_revenue=week_revenue,
        # NEW: Revenue goal
        revenue_goal=revenue_goal,
        revenue_pct=revenue_pct,
    )
