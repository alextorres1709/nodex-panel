import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session
from werkzeug.utils import secure_filename
from models import db, Document, Project, Client
from routes.auth import login_required
from services.activity import log_activity
from config import BASE_DIR

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

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    # Avoid collisions
    base, ext = os.path.splitext(filename)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{base}_{ts}{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)

    pid = request.form.get("project_id", "").strip()
    cid = request.form.get("client_id", "").strip()

    doc = Document(
        name=request.form.get("name", filename).strip() or filename,
        filename=safe_name,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type or "",
        category=request.form.get("category", "otro"),
        project_id=int(pid) if pid else None,
        client_id=int(cid) if cid else None,
        uploaded_by=uid,
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(doc)
    log_activity("create", "document", details=f"Subido: {doc.name}")
    db.session.commit()
    flash("Documento subido", "success")
    return redirect(url_for("documents.index"))


@documents_bp.route("/documentos/<int:did>/download")
@login_required
def download(did):
    doc = db.session.get(Document, did)
    if not doc or not os.path.exists(doc.file_path):
        flash("Archivo no encontrado", "error")
        return redirect(url_for("documents.index"))
    return send_file(doc.file_path, as_attachment=True, download_name=doc.filename)


@documents_bp.route("/documentos/<int:did>/delete", methods=["POST"])
@login_required
def delete(did):
    doc = db.session.get(Document, did)
    if doc:
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
        log_activity("delete", "document", doc.id, f"Eliminado: {doc.name}")
        db.session.delete(doc)
        db.session.commit()
        flash("Documento eliminado", "success")
    return redirect(url_for("documents.index"))
