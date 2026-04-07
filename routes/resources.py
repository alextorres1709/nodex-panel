import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from werkzeug.utils import secure_filename
from models import db, Resource
from routes.auth import login_required
from services.activity import log_activity
from config import BASE_DIR
from services.sync import push_change, push_change_now, sync_locked

resources_bp = Blueprint("resources", __name__)

RESOURCES_FOLDER = os.path.join(BASE_DIR, "resources_files")
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "png", "jpg", "jpeg", "gif", "svg", "webp",
    "ai", "psd", "fig", "sketch",
    "mp4", "mov", "zip", "rar", "txt", "csv",
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@resources_bp.route("/recursos")
@login_required
def index():
    cat = request.args.get("category", "")
    q = Resource.query
    if cat:
        q = q.filter_by(category=cat)
    resources = q.order_by(Resource.created_at.desc()).all()
    return render_template("recursos.html", resources=resources, sel_category=cat)


@resources_bp.route("/recursos/upload", methods=["POST"])
@login_required
def upload():
    uid = session.get("user_id")
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Selecciona un archivo", "error")
        return redirect(url_for("resources.index"))

    if not allowed_file(file.filename):
        flash("Tipo de archivo no permitido", "error")
        return redirect(url_for("resources.index"))

    os.makedirs(RESOURCES_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{base}_{ts}{ext}"
    file_path = os.path.join(RESOURCES_FOLDER, safe_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)

    res = Resource(
        name=request.form.get("name", filename).strip() or filename,
        filename=safe_name,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type or "",
        category=request.form.get("category", "otro"),
        uploaded_by=uid,
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(res)
    log_activity("create", "resource", details=f"Subido: {res.name}")
    db.session.commit()
    push_change("resources", res.id)
    flash("Recurso subido", "success")
    return redirect(url_for("resources.index"))


@resources_bp.route("/recursos/<int:rid>/download")
@login_required
def download(rid):
    res = db.session.get(Resource, rid)
    if not res or not os.path.exists(res.file_path):
        flash("Archivo no encontrado", "error")
        return redirect(url_for("resources.index"))
    return send_file(res.file_path, as_attachment=True, download_name=res.filename)


@resources_bp.route("/recursos/<int:rid>/delete", methods=["POST"])
@login_required
def delete(rid):
    res = db.session.get(Resource, rid)
    if res:
        if res.file_path and os.path.exists(res.file_path):
            os.remove(res.file_path)
        res_id = res.id
        with sync_locked():
            log_activity("delete", "resource", res.id, f"Eliminado: {res.name}")
            db.session.delete(res)
            db.session.commit()
            push_change_now("resources", res_id)
        flash("Recurso eliminado", "success")
    return redirect(url_for("resources.index"))
