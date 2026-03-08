from flask import Blueprint, render_template
from models import ActivityLog
from routes.auth import login_required

activity_bp = Blueprint("activity", __name__)


@activity_bp.route("/actividad")
@login_required
def index():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(100).all()
    return render_template("actividad.html", logs=logs)
