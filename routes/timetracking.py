from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from sqlalchemy.orm import joinedload
from models import db, TimeEntry, Task, Project, User
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change_now, sync_locked

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

    # Chart navigation: week selected
    chart_week_str = request.args.get("chart_week", "")
    if chart_week_str:
        try:
            chart_week_start = datetime.strptime(chart_week_str, "%Y-%m-%d").date()
            # Ensure it's a Monday
            chart_week_start = chart_week_start - timedelta(days=chart_week_start.weekday())
        except ValueError:
            chart_week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        chart_week_start = date.today() - timedelta(days=date.today().weekday())
        
    chart_week_end = chart_week_start + timedelta(days=6)
    prev_week = chart_week_start - timedelta(days=7)
    next_week = chart_week_start + timedelta(days=7)

    # Stats — computed via SQL aggregations instead of loading every row into Python
    from sqlalchemy import func
    week_start = date.today() - timedelta(days=date.today().weekday())
    today_minutes = sum(e.minutes for e in entries if e.date == date.today())
    week_minutes = db.session.query(func.coalesce(func.sum(TimeEntry.minutes), 0)).filter(
        TimeEntry.date >= week_start, TimeEntry.user_id == uid
    ).scalar() or 0
    month_minutes = db.session.query(func.coalesce(func.sum(TimeEntry.minutes), 0)).filter(
        db.extract("month", TimeEntry.date) == date.today().month,
        db.extract("year", TimeEntry.date) == date.today().year,
        TimeEntry.user_id == uid,
    ).scalar() or 0

    tasks = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).order_by(Task.title).all()
    projects = Project.query.order_by(Project.name).all()
    users = User.query.filter_by(active=True).all()

    # Team stats: batch-fetch week (with daily breakdown) and month totals in
    # 2 grouped queries instead of 2×N queries per user.
    week_rows = db.session.query(
        TimeEntry.user_id, TimeEntry.date, func.sum(TimeEntry.minutes)
    ).filter(
        TimeEntry.date >= chart_week_start, TimeEntry.date <= chart_week_end
    ).group_by(TimeEntry.user_id, TimeEntry.date).all()

    month_rows = db.session.query(
        TimeEntry.user_id, func.sum(TimeEntry.minutes)
    ).filter(
        db.extract("month", TimeEntry.date) == chart_week_start.month,
        db.extract("year", TimeEntry.date) == chart_week_start.year,
    ).group_by(TimeEntry.user_id).all()

    # Build per-user lookup dicts
    daily_by_user = {}   # user_id -> [0]*7
    week_totals = {}     # user_id -> int
    for user_id, d, mins in week_rows:
        mins = int(mins or 0)
        if user_id not in daily_by_user:
            daily_by_user[user_id] = [0] * 7
        daily_by_user[user_id][d.weekday()] += mins
        week_totals[user_id] = week_totals.get(user_id, 0) + mins
    month_totals = {uid_: int(mins or 0) for uid_, mins in month_rows}

    team_stats = []
    for u in users:
        team_stats.append({
            "id": u.id, "name": u.name,
            "week": week_totals.get(u.id, 0),
            "month": month_totals.get(u.id, 0),
            "daily": daily_by_user.get(u.id, [0] * 7),
        })

    return render_template(
        "timetracking.html", entries=entries, tasks=tasks, projects=projects,
        today_minutes=today_minutes, week_minutes=week_minutes, month_minutes=month_minutes,
        filter_date=filter_date, filter_project=filter_project,
        team_stats=team_stats,
        chart_week_start=chart_week_start, chart_week_end=chart_week_end,
        prev_week=prev_week, next_week=next_week
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


@timetracking_bp.route("/timetracking/<int:eid>/edit", methods=["POST"])
@login_required
def edit(eid):
    entry = db.session.get(TimeEntry, eid)
    if not entry:
        flash("Entrada no encontrada", "error")
        return redirect(url_for("timetracking.index"))
    try:
        entry.description = request.form.get("description", "").strip()
        pid = request.form.get("project_id", "").strip()
        entry.project_id = int(pid) if pid else None
        log_activity("update", "time_entry", eid, f"Editado: {entry.minutes}min")
        db.session.commit()
        from services.sync import push_change
        push_change("time_entries", eid)
        flash("Entrada actualizada", "success")
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
        with sync_locked():
            log_activity("delete", "time_entry", entry.id, f"{entry.minutes}min eliminados")
            db.session.delete(entry)
            db.session.commit()
            push_change_now("time_entries", eid_copy)
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
