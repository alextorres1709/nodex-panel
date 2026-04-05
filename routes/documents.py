import os
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from werkzeug.utils import secure_filename
from models import db, Document, Project, Client
from routes.auth import login_required
from services.activity import log_activity
from config import BASE_DIR
from services.sync import push_change
from services import gdrive

documents_bp = Blueprint("documents", __name__)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "gif", "txt", "csv", "zip"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_mime_icon(mime_type):
    if "pdf" in mime_type:
        return "pdf"
    if "image" in mime_type:
        return "img"
    if "word" in mime_type or "document" in mime_type:
        return "doc"
    return "other"


@documents_bp.route("/documentos")
@login_required
def index():
    cat = request.args.get("category", "")
    pid = request.args.get("project_id", "")

    q = Document.query
    if cat:
        q = q.filter_by(category=cat)
    if pid:
        q = q.filter_by(project_id=int(pid))

    docs = q.order_by(Document.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    clients = Client.query.order_by(Client.name).all()

    return render_template("documentos.html", docs=docs, projects=projects, clients=clients,
                           sel_category=cat, sel_project=pid)


@documents_bp.route("/documentos/upload", methods=["POST"])
@login_required
def upload():
    uid = session.get("user_id")
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Selecciona un archivo", "error")
        return redirect(url_for("documents.index"))

    if not allowed_file(file.filename):
        flash("Tipo de archivo no permitido", "error")
        return redirect(url_for("documents.index"))

    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{base}_{ts}{ext}"
    mime_type = file.content_type or "application/octet-stream"

    drive_file_id = ""
    file_path = ""
    file_size = 0

    # ── Try Google Drive first ──
    if gdrive.is_available():
        file_bytes = file.read()
        file_size = len(file_bytes)
        file_stream = io.BytesIO(file_bytes)

        drive_file_id = gdrive.upload_file(file_stream, safe_name, mime_type)

        if not drive_file_id:
            # Drive failed — fall back to local
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file_path = os.path.join(UPLOAD_FOLDER, safe_name)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
    else:
        # ── Local storage fallback ──
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(file_path)
        file_size = os.path.getsize(file_path)

    pid = request.form.get("project_id", "").strip()
    cid = request.form.get("client_id", "").strip()

    doc = Document(
        name=request.form.get("name", filename).strip() or filename,
        filename=safe_name,
        file_path=file_path,
        drive_file_id=drive_file_id,
        file_size=file_size,
        mime_type=mime_type,
        category=request.form.get("category", "otro"),
        project_id=int(pid) if pid else None,
        client_id=int(cid) if cid else None,
        uploaded_by=uid,
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(doc)
    log_activity("create", "document", details=f"Subido: {doc.name}")
    db.session.commit()
    push_change("documents", doc.id)
    flash("Documento subido", "success")
    return redirect(url_for("documents.index"))


@documents_bp.route("/documentos/<int:did>/download")
@login_required
def download(did):
    doc = db.session.get(Document, did)
    if not doc:
        flash("Documento no encontrado", "error")
        return redirect(url_for("documents.index"))

    # ── Try Google Drive first ──
    if doc.drive_file_id:
        buffer = gdrive.download_file(doc.drive_file_id)
        if buffer:
            return send_file(
                buffer,
                as_attachment=True,
                download_name=doc.filename,
                mimetype=doc.mime_type or "application/octet-stream",
            )

    # ── Local file fallback ──
    if doc.file_path and os.path.exists(doc.file_path):
        return send_file(doc.file_path, as_attachment=True, download_name=doc.filename)

    flash("Archivo no encontrado", "error")
    return redirect(url_for("documents.index"))


@documents_bp.route("/documentos/<int:did>/delete", methods=["POST"])
@login_required
def delete(did):
    doc = db.session.get(Document, did)
    if doc:
        if doc.drive_file_id:
            gdrive.delete_file(doc.drive_file_id)
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
        doc_id = doc.id
        log_activity("delete", "document", doc.id, f"Eliminado: {doc.name}")
        db.session.delete(doc)
        db.session.commit()
        push_change("documents", doc_id)
        flash("Documento eliminado", "success")
    return redirect(url_for("documents.index"))
