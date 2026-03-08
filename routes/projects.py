from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Project
from routes.auth import login_required
from services.activity import log_activity

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/proyectos")
@login_required
def index():
    status = request.args.get("status", "")
    ptype = request.args.get("type", "")
    q = Project.query
    if status:
        q = q.filter_by(status=status)
    if ptype:
        q = q.filter_by(type=ptype)
    projects = q.order_by(Project.created_at.desc()).all()
    return render_template("proyectos.html", projects=projects, sel_status=status, sel_type=ptype)


@projects_bp.route("/proyectos/create", methods=["POST"])
@login_required
def create():
    try:
        dl = request.form.get("deadline", "").strip()
        p = Project(
            name=request.form.get("name", "").strip(),
            client_name=request.form.get("client_name", "").strip(),
            status=request.form.get("status", "activo"),
            type=request.form.get("type", "web"),
            budget=float(request.form.get("budget", 0) or 0),
            progress=int(request.form.get("progress", 0) or 0),
            deadline=datetime.strptime(dl, "%Y-%m-%d").date() if dl else None,
            description=request.form.get("description", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(p)
        log_activity("create", "project", details=f"Nuevo proyecto: {p.name}")
        db.session.commit()
        flash("Proyecto creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.index"))


@projects_bp.route("/proyectos/edit/<int:pid>", methods=["POST"])
@login_required
def edit(pid):
    p = db.session.get(Project, pid)
    if not p:
        flash("Proyecto no encontrado", "error")
        return redirect(url_for("projects.index"))
    try:
        p.name = request.form.get("name", p.name).strip()
        p.client_name = request.form.get("client_name", p.client_name).strip()
        p.status = request.form.get("status", p.status)
        p.type = request.form.get("type", p.type)
        p.budget = float(request.form.get("budget", p.budget) or 0)
        p.progress = int(request.form.get("progress", p.progress) or 0)
        dl = request.form.get("deadline", "").strip()
        p.deadline = datetime.strptime(dl, "%Y-%m-%d").date() if dl else None
        p.description = request.form.get("description", "").strip()
        p.notes = request.form.get("notes", "").strip()
        log_activity("update", "project", p.id, f"Editado: {p.name}")
        db.session.commit()
        flash("Proyecto actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.index"))


@projects_bp.route("/proyectos/delete/<int:pid>", methods=["POST"])
@login_required
def delete(pid):
    p = db.session.get(Project, pid)
    if p:
        log_activity("delete", "project", p.id, f"Eliminado: {p.name}")
        db.session.delete(p)
        db.session.commit()
        flash("Proyecto eliminado", "success")
    return redirect(url_for("projects.index"))
