import os
import io
import threading
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from werkzeug.utils import secure_filename
from models import db, Resource
from routes.auth import login_required
from services.activity import log_activity
from config import BASE_DIR, GOOGLE_DRIVE_RESOURCES_FOLDER_ID
from services.sync import push_change, push_change_now, sync_locked
from services import gdrive

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
    return render_template(
        "recursos.html",
        resources=resources,
        sel_category=cat,
        gdrive_connected=gdrive.is_available(),
        gdrive_needs_auth=gdrive.needs_authorization(),
    )


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

    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{base}_{ts}{ext}"
    mime_type = file.content_type or "application/octet-stream"

    drive_file_id = ""
    file_path = ""
    file_size = 0

    # ── Try Google Drive first (carpeta separada de documentos) ──
    if gdrive.is_available():
        file_bytes = file.read()
        file_size = len(file_bytes)
        file_stream = io.BytesIO(file_bytes)
        drive_file_id = gdrive.upload_file(
            file_stream, safe_name, mime_type,
            parent_folder_id=GOOGLE_DRIVE_RESOURCES_FOLDER_ID,
        )
        if not drive_file_id:
            # Drive failed — fall back to local
            os.makedirs(RESOURCES_FOLDER, exist_ok=True)
            file_path = os.path.join(RESOURCES_FOLDER, safe_name)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
    else:
        # ── Local storage fallback ──
        os.makedirs(RESOURCES_FOLDER, exist_ok=True)
        file_path = os.path.join(RESOURCES_FOLDER, safe_name)
        file.save(file_path)
        file_size = os.path.getsize(file_path)

    res = Resource(
        name=request.form.get("name", filename).strip() or filename,
        filename=safe_name,
        file_path=file_path,
        drive_file_id=drive_file_id,
        file_size=file_size,
        mime_type=mime_type,
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


def _serve_resource(res, as_attachment):
    """Stream a resource from Drive (preferred) or local disk fallback."""
    if res.drive_file_id:
        buffer = gdrive.download_file(res.drive_file_id)
        if buffer:
            return send_file(
                buffer,
                as_attachment=as_attachment,
                download_name=res.filename,
                mimetype=res.mime_type or "application/octet-stream",
            )
    if res.file_path and os.path.exists(res.file_path):
        return send_file(
            res.file_path,
            as_attachment=as_attachment,
            download_name=res.filename,
            mimetype=res.mime_type or "application/octet-stream",
        )
    return None


@resources_bp.route("/recursos/<int:rid>/download")
@login_required
def download(rid):
    res = db.session.get(Resource, rid)
    if not res:
        flash("Recurso no encontrado", "error")
        return redirect(url_for("resources.index"))
    resp = _serve_resource(res, as_attachment=True)
    if resp is None:
        flash("Archivo no encontrado", "error")
        return redirect(url_for("resources.index"))
    return resp


@resources_bp.route("/recursos/<int:rid>/preview")
@login_required
def preview(rid):
    res = db.session.get(Resource, rid)
    if not res:
        flash("Recurso no encontrado", "error")
        return redirect(url_for("resources.index"))
    resp = _serve_resource(res, as_attachment=False)
    if resp is None:
        flash("Archivo no encontrado", "error")
        return redirect(url_for("resources.index"))
    return resp


@resources_bp.route("/recursos/<int:rid>/delete", methods=["POST"])
@login_required
def delete(rid):
    res = db.session.get(Resource, rid)
    if res:
        drive_file_id = res.drive_file_id
        local_path = res.file_path
        res_id = res.id
        with sync_locked():
            log_activity("delete", "resource", res.id, f"Eliminado: {res.name}")
            db.session.delete(res)
            db.session.commit()
            push_change_now("resources", res_id)

        # Cleanup remoto en background para no bloquear el request
        def _cleanup_storage():
            try:
                if drive_file_id:
                    gdrive.delete_file(drive_file_id)
            except Exception:
                pass
            try:
                if local_path and os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
        threading.Thread(target=_cleanup_storage, daemon=True).start()

        flash("Recurso eliminado", "success")
    return redirect(url_for("resources.index"))
