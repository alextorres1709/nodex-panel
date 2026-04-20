"""
CRUD de plantillas de email (/plantillas-email).

Las plantillas usan placeholders {empresa}, {contacto}, {nombre_remitente}
que se renderizan en el panel antes de encolar el email a n8n.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, EmailTemplate, EMAIL_TEMPLATE_CATEGORIES
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

email_templates_bp = Blueprint("email_templates", __name__)


@email_templates_bp.route("/plantillas-email")
@login_required
def index():
    category = request.args.get("category", "")
    q = EmailTemplate.query
    if category:
        q = q.filter_by(category=category)
    templates = q.order_by(EmailTemplate.step_order.asc(), EmailTemplate.created_at.desc()).all()
    return render_template("plantillas_email.html",
                           templates=templates, categories=EMAIL_TEMPLATE_CATEGORIES,
                           selected_category=category)


@email_templates_bp.route("/plantillas-email/create", methods=["POST"])
@login_required
def create():
    try:
        step = request.form.get("step_order", "1").strip() or "1"
        tpl = EmailTemplate(
            name=request.form.get("name", "").strip(),
            category=request.form.get("category", "intro"),
            step_order=int(step) if step.isdigit() else 1,
            subject=request.form.get("subject", "").strip(),
            body=request.form.get("body", "").strip(),
            active=True,
        )
        db.session.add(tpl)
        log_activity("create", "email_template", details=f"Plantilla: {tpl.name}")
        db.session.commit()
        push_change("email_templates", tpl.id)
        flash("Plantilla creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("email_templates.index"))


@email_templates_bp.route("/plantillas-email/edit/<int:tid>", methods=["POST"])
@login_required
def edit(tid):
    tpl = db.session.get(EmailTemplate, tid)
    if not tpl:
        flash("Plantilla no encontrada", "error")
        return redirect(url_for("email_templates.index"))
    try:
        tpl.name = request.form.get("name", tpl.name).strip()
        tpl.category = request.form.get("category", tpl.category)
        step = request.form.get("step_order", "").strip()
        if step.isdigit():
            tpl.step_order = int(step)
        tpl.subject = request.form.get("subject", "").strip()
        tpl.body = request.form.get("body", "").strip()
        tpl.active = request.form.get("active") == "on"
        log_activity("update", "email_template", tpl.id, f"Editada: {tpl.name}")
        db.session.commit()
        push_change("email_templates", tpl.id)
        flash("Plantilla actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("email_templates.index"))


@email_templates_bp.route("/plantillas-email/delete/<int:tid>", methods=["POST"])
@login_required
def delete(tid):
    tpl = db.session.get(EmailTemplate, tid)
    if tpl:
        tid_val = tpl.id
        with sync_locked():
            log_activity("delete", "email_template", tpl.id, f"Eliminada: {tpl.name}")
            db.session.delete(tpl)
            db.session.commit()
            push_change_now("email_templates", tid_val)
        flash("Plantilla eliminada", "success")
    return redirect(url_for("email_templates.index"))
