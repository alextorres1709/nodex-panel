from flask import Blueprint, render_template
from routes.auth import login_required

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/configuracion")
@login_required
def index():
    return render_template("configuracion.html")
