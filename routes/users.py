from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, User
from routes.auth import admin_required
from services.activity import log_activity

users_bp = Blueprint("users", __name__)


@users_bp.route("/usuarios")
@admin_required
def index():
    users = User.query.order_by(User.created_at).all()
    return render_template("usuarios.html", users=users)


@users_bp.route("/usuarios/create", methods=["POST"])
@admin_required
def create():
    try:
        email = request.form.get("email", "").strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email ya registrado", "error")
            return redirect(url_for("users.index"))
        u = User(
            name=request.form.get("name", "").strip(),
            email=email,
            role=request.form.get("role", "editor"),
        )
        u.set_password(request.form.get("password", "nodex2024"))
        db.session.add(u)
        log_activity("create", "user", details=f"Nuevo usuario: {u.name}")
        db.session.commit()
        flash("Usuario creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("users.index"))


@users_bp.route("/usuarios/edit/<int:uid>", methods=["POST"])
@admin_required
def edit(uid):
    u = db.session.get(User, uid)
    if not u:
        flash("Usuario no encontrado", "error")
        return redirect(url_for("users.index"))
    try:
        u.name = request.form.get("name", u.name).strip()
        u.email = request.form.get("email", u.email).strip().lower()
        u.role = request.form.get("role", u.role)
        u.active = request.form.get("active") == "on"
        pw = request.form.get("password", "").strip()
        if pw:
            u.set_password(pw)
        log_activity("update", "user", u.id, f"Editado: {u.name}")
        db.session.commit()
        flash("Usuario actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("users.index"))


@users_bp.route("/usuarios/delete/<int:uid>", methods=["POST"])
@admin_required
def delete(uid):
    if g.get("user") and g.user.id == uid:
        flash("No puedes eliminarte a ti mismo", "error")
        return redirect(url_for("users.index"))
    u = db.session.get(User, uid)
    if u:
        log_activity("delete", "user", u.id, f"Eliminado: {u.name}")
        db.session.delete(u)
        db.session.commit()
        from services.sync import push_change
        push_change("users", uid)
        flash("Usuario eliminado", "success")
    return redirect(url_for("users.index"))
