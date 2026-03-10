from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template
from models import db, Payment, Project, Task, Idea, ActivityLog
from routes.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    # All queries now hit local SQLite (~0.1ms each instead of ~150ms)
    rows = Payment.query.filter_by(status="activo").all()
    monthly_cost = sum(
        p.amount if p.frequency == "mensual" else p.amount / 12 if p.frequency == "anual" else 0
        for p in rows
    )
    active_projects = Project.query.filter_by(status="activo").count()
    pending_tasks = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count()
    new_ideas = Idea.query.filter_by(status="nueva").count()

    cost_chart = (
        db.session.query(Payment.category, db.func.sum(Payment.amount))
        .filter_by(status="activo", frequency="mensual")
        .group_by(Payment.category)
        .all()
    )
    cost_labels = [r[0] for r in cost_chart]
    cost_values = [float(r[1] or 0) for r in cost_chart]

    proj_chart = (
        db.session.query(Project.status, db.func.count(Project.id))
        .group_by(Project.status)
        .all()
    )
    proj_labels = [r[0] for r in proj_chart]
    proj_values = [r[1] for r in proj_chart]

    urgent_tasks = (
        Task.query
        .options(joinedload(Task.assignee))
        .filter(Task.status.in_(["pendiente", "en_progreso"]))
        .order_by(Task.due_date.asc().nullslast(), Task.priority.desc())
        .limit(5)
        .all()
    )

    recent_activity = (
        ActivityLog.query
        .options(joinedload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "dashboard.html",
        monthly_cost=monthly_cost,
        active_projects=active_projects,
        pending_tasks=pending_tasks,
        new_ideas=new_ideas,
        cost_labels=cost_labels,
        cost_values=cost_values,
        proj_labels=proj_labels,
        proj_values=proj_values,
        urgent_tasks=urgent_tasks,
        recent_activity=recent_activity,
    )
