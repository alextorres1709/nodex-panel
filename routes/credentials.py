from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Credential
from routes.auth import login_required
from services.activity import log_activity

credentials_bp = Blueprint("credentials", __name__)


@credentials_bp.route("/credenciales")
@login_required
def index():
    cat = request.args.get("category", "")
    q = Credential.query
    if cat:
        q = q.filter_by(category=cat)
    creds = q.order_by(Credential.service).all()
    return render_template("credenciales.html", creds=creds, sel_category=cat)


@credentials_bp.route("/credenciales/create", methods=["POST"])
@login_required
def create():
    try:
        c = Credential(
            service=request.form.get("service", "").strip(),
            url=request.form.get("url", "").strip(),
            username=request.form.get("username", "").strip(),
            email=request.form.get("email", "").strip(),
            password=request.form.get("password", "").strip(),
            api_key=request.form.get("api_key", "").strip(),
            notes=request.form.get("notes", "").strip(),
            category=request.form.get("category", "otro"),
        )
        db.session.add(c)
        log_activity("create", "credential", details=f"Nueva credencial: {c.service}")
        db.session.commit()
        flash("Credencial guardada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("credentials.index"))


@credentials_bp.route("/credenciales/edit/<int:cid>", methods=["POST"])
@login_required
def edit(cid):
    c = db.session.get(Credential, cid)
    if not c:
        flash("Credencial no encontrada", "error")
        return redirect(url_for("credentials.index"))
    try:
        c.service = request.form.get("service", c.service).strip()
        c.url = request.form.get("url", c.url).strip()
        c.username = request.form.get("username", "").strip()
        c.email = request.form.get("email", "").strip()
        c.password = request.form.get("password", "").strip()
        c.api_key = request.form.get("api_key", "").strip()
        c.notes = request.form.get("notes", "").strip()
        c.category = request.form.get("category", c.category)
        log_activity("update", "credential", c.id, f"Editada: {c.service}")
        db.session.commit()
        flash("Credencial actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("credentials.index"))


@credentials_bp.route("/credenciales/delete/<int:cid>", methods=["POST"])
@login_required
def delete(cid):
    c = db.session.get(Credential, cid)
    if c:
        log_activity("delete", "credential", c.id, f"Eliminada: {c.service}")
        db.session.delete(c)
        db.session.commit()
        flash("Credencial eliminada", "success")
    return redirect(url_for("credentials.index"))
