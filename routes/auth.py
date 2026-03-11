from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify
from models import db, User, ROLE_PERMISSIONS
from services.activity import log_activity

auth_bp = Blueprint("auth", __name__)


def _load_current_user():
    if request.path.startswith('/static/'):
        return
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


def permission_required(module, action="read"):
    """Decorator that checks granular module-level permissions."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not g.get("user"):
                return redirect(url_for("auth.login"))
            if not g.user.has_permission(module, action):
                flash(f"No tienes permisos para {action} en {module}", "error")
                return redirect(url_for("dashboard.index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def api_token_required(f):
    """Decorator for REST API endpoints — authenticates via Bearer token or session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Try Bearer token first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user = User.query.filter_by(api_token=token, active=True).first()
            if user:
                g.api_user = user
                return f(*args, **kwargs)
            return jsonify({"error": "Invalid or expired token"}), 401
        # Fall back to session auth
        if g.get("user"):
            g.api_user = g.user
            return f(*args, **kwargs)
        return jsonify({"error": "Authentication required. Use Bearer token or session cookie."}), 401
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
