from flask import Blueprint, render_template
from routes.auth import login_required

captacion_bp = Blueprint("captacion", __name__)


@captacion_bp.route("/captacion")
@login_required
def index():
    return render_template("captacion.html")
