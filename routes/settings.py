import sys
from flask import Blueprint, render_template, redirect, url_for, flash, g
from config import Config, APP_VERSION
from models import db
from routes.auth import login_required

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/configuracion")
@login_required
def index():
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    return render_template(
        "configuracion.html",
        app_version=APP_VERSION,
        db_path=db_path,
        python_version=python_version,
    )


@settings_bp.route("/configuracion/regenerate-token", methods=["POST"])
@login_required
def regenerate_token():
    user = g.user
    token = user.generate_api_token()
    db.session.commit()
    flash(f"Token regenerado: {token[:8]}...{token[-8:]}", "success")
    return redirect(url_for("settings.index"))
