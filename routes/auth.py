from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from models import db, User
from services.activity import log_activity

auth_bp = Blueprint("auth", __name__)


def _load_current_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = db.session.get(User, uid)
        if g.user and not g.user.active:
            session.clear()
            g.user = None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login"))
        if not g.user.is_admin:
            flash("No tienes permisos de administrador", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(password):
            remember = request.form.get("remember")
            if remember:
                session.permanent = True
            session["user_id"] = user.id
            g.user = user
            log_activity("login", "user", user.id, f"Login: {user.name}")
            db.session.commit()
            return redirect(url_for("dashboard.index"))
        flash("Credenciales incorrectas", "error")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
