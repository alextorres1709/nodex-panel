from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import joinedload
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, current_app
from models import db, Idea, Project
from routes.auth import login_required
from services.activity import log_activity

ideas_bp = Blueprint("ideas", __name__)


def _run_in_app(app, fn):
    with app.app_context():
        return fn()


@ideas_bp.route("/ideas")
@login_required
def index():
    app = current_app._get_current_object()
    status = request.args.get("status", "")
    cat = request.args.get("category", "")

    def q_ideas():
        q = Idea.query.options(joinedload(Idea.author), joinedload(Idea.project))
        if status:
            q = q.filter_by(status=status)
        if cat:
            q = q.filter_by(category=cat)
        return q.order_by(Idea.votes.desc(), Idea.created_at.desc()).all()

    def q_projects():
        return Project.query.order_by(Project.name).all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ideas = pool.submit(_run_in_app, app, q_ideas)
        f_projects = pool.submit(_run_in_app, app, q_projects)

    ideas = f_ideas.result()
    projects = f_projects.result()
    return render_template("ideas.html", ideas=ideas, projects=projects, sel_status=status, sel_category=cat)


@ideas_bp.route("/ideas/create", methods=["POST"])
@login_required
def create():
    try:
        pid = request.form.get("project_id", "").strip()
        idea = Idea(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            category=request.form.get("category", "feature"),
            project_id=int(pid) if pid else None,
            status="nueva",
            created_by=g.user.id,
        )
        db.session.add(idea)
        log_activity("create", "idea", details=f"Nueva idea: {idea.title}")
        db.session.commit()
        flash("Idea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("ideas.index"))


@ideas_bp.route("/ideas/edit/<int:iid>", methods=["POST"])
@login_required
def edit(iid):
    idea = db.session.get(Idea, iid)
    if not idea:
        flash("Idea no encontrada", "error")
        return redirect(url_for("ideas.index"))
    try:
        idea.title = request.form.get("title", idea.title).strip()
        idea.description = request.form.get("description", "").strip()
        idea.category = request.form.get("category", idea.category)
        idea.status = request.form.get("status", idea.status)
        pid = request.form.get("project_id", "").strip()
        idea.project_id = int(pid) if pid else None
        log_activity("update", "idea", idea.id, f"Editada: {idea.title}")
        db.session.commit()
        flash("Idea actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("ideas.index"))


@ideas_bp.route("/ideas/vote/<int:iid>", methods=["POST"])
@login_required
def vote(iid):
    idea = db.session.get(Idea, iid)
    if idea:
        idea.votes += 1
        log_activity("vote", "idea", idea.id, f"+1: {idea.title}")
        db.session.commit()
    return redirect(url_for("ideas.index"))


@ideas_bp.route("/ideas/delete/<int:iid>", methods=["POST"])
@login_required
def delete(iid):
    idea = db.session.get(Idea, iid)
    if idea:
        log_activity("delete", "idea", idea.id, f"Eliminada: {idea.title}")
        db.session.delete(idea)
        db.session.commit()
        flash("Idea eliminada", "success")
    return redirect(url_for("ideas.index"))
