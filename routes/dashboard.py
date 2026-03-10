from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, current_app
from models import db, Payment, Project, Task, Idea, ActivityLog
from routes.auth import login_required
from services.cache import cache_get, cache_set

dashboard_bp = Blueprint("dashboard", __name__)

CACHE_KEY = "dashboard_data"
CACHE_TTL = 15  # seconds


def _run_in_app(app, fn):
    """Run a DB query function inside a Flask app context (for threads)."""
    with app.app_context():
        return fn()


def _fetch_dashboard_data(app):
    """Fetch all dashboard data using parallel threads."""
    def q_payments():
        rows = Payment.query.filter_by(status="activo").all()
        return sum(
            p.amount if p.frequency == "mensual" else p.amount / 12 if p.frequency == "anual" else 0
            for p in rows
        )

    def q_active_projects():
        return Project.query.filter_by(status="activo").count()

    def q_pending_tasks():
        return Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count()

    def q_new_ideas():
        return Idea.query.filter_by(status="nueva").count()

    def q_cost_chart():
        rows = (
            db.session.query(Payment.category, db.func.sum(Payment.amount))
            .filter_by(status="activo", frequency="mensual")
            .group_by(Payment.category)
            .all()
        )
        return [r[0] for r in rows], [float(r[1] or 0) for r in rows]

    def q_proj_chart():
        rows = (
            db.session.query(Project.status, db.func.count(Project.id))
            .group_by(Project.status)
            .all()
        )
        return [r[0] for r in rows], [r[1] for r in rows]

    def q_urgent_tasks():
        return (
            Task.query
            .options(joinedload(Task.assignee))
            .filter(Task.status.in_(["pendiente", "en_progreso"]))
            .order_by(Task.due_date.asc().nullslast(), Task.priority.desc())
            .limit(5)
            .all()
        )

    def q_recent_activity():
        return (
            ActivityLog.query
            .options(joinedload(ActivityLog.user))
            .order_by(ActivityLog.created_at.desc())
            .limit(8)
            .all()
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        f_cost = pool.submit(_run_in_app, app, q_payments)
        f_projects = pool.submit(_run_in_app, app, q_active_projects)
        f_tasks = pool.submit(_run_in_app, app, q_pending_tasks)
        f_ideas = pool.submit(_run_in_app, app, q_new_ideas)
        f_cost_chart = pool.submit(_run_in_app, app, q_cost_chart)
        f_proj_chart = pool.submit(_run_in_app, app, q_proj_chart)
        f_urgent = pool.submit(_run_in_app, app, q_urgent_tasks)
        f_activity = pool.submit(_run_in_app, app, q_recent_activity)

    cost_labels, cost_values = f_cost_chart.result()
    proj_labels, proj_values = f_proj_chart.result()

    return {
        "monthly_cost": f_cost.result(),
        "active_projects": f_projects.result(),
        "pending_tasks": f_tasks.result(),
        "new_ideas": f_ideas.result(),
        "cost_labels": cost_labels,
        "cost_values": cost_values,
        "proj_labels": proj_labels,
        "proj_values": proj_values,
        "urgent_tasks": f_urgent.result(),
        "recent_activity": f_activity.result(),
    }


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    # Try cache first — avoids ALL DB queries for 15 seconds
    data = cache_get(CACHE_KEY)
    if not data:
        app = current_app._get_current_object()
        data = _fetch_dashboard_data(app)
        cache_set(CACHE_KEY, data, CACHE_TTL)

    return render_template("dashboard.html", **data)
