from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from sqlalchemy.orm import joinedload
from models import db, TimeEntry, Task, Project, User
from routes.auth import login_required
from services.activity import log_activity

timetracking_bp = Blueprint("timetracking", __name__)


@timetracking_bp.route("/timetracking")
@login_required
def index():
    uid = session.get("user_id")
    filter_date = request.args.get("date", "")
    filter_project = request.args.get("project_id", "")

    q = TimeEntry.query.options(
        joinedload(TimeEntry.task), joinedload(TimeEntry.project), joinedload(TimeEntry.user)
    )

    if filter_date:
        d = datetime.strptime(filter_date, "%Y-%m-%d").date()
        q = q.filter(TimeEntry.date == d)
    if filter_project:
        q = q.filter_by(project_id=int(filter_project))

    entries = q.order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc()).all()

    # Stats
    today_minutes = sum(e.minutes for e in entries if e.date == date.today())
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_entries = TimeEntry.query.filter(TimeEntry.date >= week_start, TimeEntry.user_id == uid).all()
    week_minutes = sum(e.minutes for e in week_entries)
    month_entries = TimeEntry.query.filter(
        db.extract("month", TimeEntry.date) == date.today().month,
        db.extract("year", TimeEntry.date) == date.today().year,
        TimeEntry.user_id == uid,
    ).all()
    month_minutes = sum(e.minutes for e in month_entries)

    tasks = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).order_by(Task.title).all()
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).all()

    # Team stats: week and month minutes per user
    team_stats = []
    for u in users:
        u_week = sum(e.minutes for e in TimeEntry.query.filter(
            TimeEntry.date >= week_start, TimeEntry.user_id == u.id).all())
        u_month = sum(e.minutes for e in TimeEntry.query.filter(
            db.extract("month", TimeEntry.date) == date.today().month,
            db.extract("year", TimeEntry.date) == date.today().year,
            TimeEntry.user_id == u.id).all())
        team_stats.append({"name": u.name, "week": u_week, "month": u_month})

    return render_template(
        "timetracking.html", entries=entries, tasks=tasks, projects=projects,
        today_minutes=today_minutes, week_minutes=week_minutes, month_minutes=month_minutes,
        filter_date=filter_date, filter_project=filter_project,
        team_stats=team_stats,
    )


@timetracking_bp.route("/timetracking/create", methods=["POST"])
@login_required
def create():
    uid = session.get("user_id")
    try:
        tid = request.form.get("task_id", "").strip()
        pid = request.form.get("project_id", "").strip()
        d = request.form.get("date", "").strip()
        mins = request.form.get("minutes", "0").strip()

        entry = TimeEntry(
            user_id=uid,
            task_id=int(tid) if tid else None,
            project_id=int(pid) if pid else None,
            description=request.form.get("description", "").strip(),
            minutes=int(mins) if mins else 0,
            date=datetime.strptime(d, "%Y-%m-%d").date() if d else date.today(),
        )
        db.session.add(entry)
        log_activity("create", "time_entry", details=f"{entry.minutes}min")
        db.session.commit()
        from services.sync import push_change
        push_change("time_entries", entry.id)
        flash("Tiempo registrado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("timetracking.index"))


@timetracking_bp.route("/timetracking/<int:eid>/delete", methods=["POST"])
@login_required
def delete(eid):
    entry = db.session.get(TimeEntry, eid)
    if entry:
        eid_copy = entry.id
        log_activity("delete", "time_entry", entry.id, f"{entry.minutes}min eliminados")
        db.session.delete(entry)
        db.session.commit()
        from services.sync import push_change
        push_change("time_entries", eid_copy)
        flash("Entrada eliminada", "success")
    return redirect(url_for("timetracking.index"))


@timetracking_bp.route("/api/timetracking/stop", methods=["POST"])
@login_required
def api_stop_timer():
    """Called by JS timer when stopped — creates a time entry."""
    uid = session.get("user_id")
    data = request.get_json(force=True)
    minutes = int(data.get("minutes", 0))
    if minutes < 1:
        return jsonify({"error": "min 1 minute"}), 400

    entry = TimeEntry(
        user_id=uid,
        task_id=data.get("task_id") or None,
        project_id=data.get("project_id") or None,
        description=data.get("description", "Timer"),
        minutes=minutes,
        date=date.today(),
    )
    db.session.add(entry)
    log_activity("create", "time_entry", details=f"Timer: {minutes}min")
    db.session.commit()
    from services.sync import push_change
    push_change("time_entries", entry.id)
    return jsonify({"ok": True, "id": entry.id, "minutes": entry.minutes})
