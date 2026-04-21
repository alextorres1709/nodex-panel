"""
Email outbox + timeline de interacciones por empresa.

Flujo Apollo-style:
- Usuario abre el modal "Enviar email" en /empresas/<cid>
- Selecciona contacto + plantilla → el panel renderiza {empresa}, {contacto},
  {nombre_remitente} en subject/body y crea una CompanyInteraction con
  status="queued".
- n8n tira de GET /api/companies/outbox cada N minutos, envía vía Gmail/SMTP
  y llama POST /api/companies/mark-sent/<id> al terminar.
- El timeline en la ficha muestra email/llamada/reunión/nota en orden DESC.
"""
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, redirect, url_for, flash, abort, jsonify, g
from sqlalchemy.orm import joinedload

from models import (
    db, Company, CompanyContact, CompanyInteraction, EmailTemplate, User, Task,
)
from routes.auth import login_required, api_token_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

company_emails_bp = Blueprint("company_emails", __name__)


# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def _render(text, empresa, contacto, sender):
    """Reemplaza {empresa}, {contacto}, {nombre_remitente} en plantillas."""
    if not text:
        return ""
    return (
        text.replace("{empresa}", empresa or "")
            .replace("{contacto}", contacto or "")
            .replace("{nombre_remitente}", sender or "")
    )


def _auto_advance_status(company, action):
    """Avanza el pipeline automáticamente al registrar acciones comerciales."""
    # Si aún está en 'por_escribir' o 'contactada_sin_respuesta', subirlo
    early = {"por_escribir", "contactada_sin_respuesta"}
    if company.status in early:
        if action == "email":
            company.status = "contactada_sin_respuesta"
        elif action in ("call", "meeting"):
            company.status = "interesado"


# ═══════════════════════════════════════════
# ENVIAR EMAIL (cola a n8n)
# ═══════════════════════════════════════════

@company_emails_bp.route("/empresas/<int:cid>/email/send", methods=["POST"])
@login_required
def send_email(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)
    try:
        contact_id = request.form.get("contact_id", "").strip()
        tpl_id = request.form.get("template_id", "").strip()
        custom_subject = request.form.get("subject", "").strip()
        custom_body = request.form.get("body", "").strip()

        contact = None
        if contact_id:
            contact = db.session.get(CompanyContact, int(contact_id))
            if not contact or contact.company_id != cid:
                flash("Contacto inválido", "error")
                return redirect(url_for("companies.view", cid=cid))

        template = None
        if tpl_id:
            template = db.session.get(EmailTemplate, int(tpl_id))

        # Decidir subject/body: prioriza lo que escribió el usuario en el modal
        raw_subject = custom_subject or (template.subject if template else "")
        raw_body = custom_body or (template.body if template else "")

        sender_name = (g.user.name if g.get("user") else "") or ""
        contact_name = (contact.name if contact else "").split(" ")[0] if contact else ""

        subject = _render(raw_subject, company.name, contact_name, sender_name)
        body = _render(raw_body, company.name, contact_name, sender_name)

        to_email = (contact.email if contact else "").strip()
        if not to_email:
            flash("El contacto no tiene email — añade uno antes de enviar", "error")
            return redirect(url_for("companies.view", cid=cid))

        interaction = CompanyInteraction(
            company_id=cid,
            contact_id=contact.id if contact else None,
            user_id=g.user.id if g.get("user") else None,
            type="email",
            status="queued",  # n8n lo recogerá
            subject=subject,
            body=body,
            to_email=to_email,
            template_id=template.id if template else None,
        )
        db.session.add(interaction)
        _auto_advance_status(company, "email")
        log_activity("email_queue", "company", cid,
                     f"Email encolado para {contact.name if contact else '?'} ({to_email})")
        db.session.commit()
        push_change("company_interactions", interaction.id)
        push_change("companies", cid)
        flash("Email encolado — n8n lo enviará en pocos minutos", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


# ═══════════════════════════════════════════
# LOG LLAMADA / REUNIÓN / NOTA
# ═══════════════════════════════════════════

@company_emails_bp.route("/empresas/<int:cid>/interactions/log", methods=["POST"])
@login_required
def log_interaction(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)
    try:
        itype = request.form.get("type", "note").strip()
        if itype not in ("call", "meeting", "note"):
            flash("Tipo inválido", "error")
            return redirect(url_for("companies.view", cid=cid))
        contact_id = request.form.get("contact_id", "").strip()
        lead_id = request.form.get("lead_id", "").strip()
        contact = None
        lead = None
        if contact_id:
            c = db.session.get(CompanyContact, int(contact_id))
            if c and c.company_id == cid:
                contact = c
        if lead_id:
            from models import Lead
            l = db.session.get(Lead, int(lead_id))
            if l:
                lead = l
        body = request.form.get("body", "").strip()
        subject = request.form.get("subject", "").strip() or {
            "call": "Llamada registrada",
            "meeting": "Reunión registrada",
            "note": "Nota",
        }[itype]

        interaction = CompanyInteraction(
            company_id=cid,
            contact_id=contact.id if contact else None,
            lead_id=lead.id if lead else None,
            user_id=g.user.id if g.get("user") else None,
            type=itype,
            status="done",
            subject=subject,
            body=body,
        )
        db.session.add(interaction)
        _auto_advance_status(company, itype)
        log_activity(f"log_{itype}", "company", cid, subject)
        db.session.commit()
        push_change("company_interactions", interaction.id)
        push_change("companies", cid)
        flash("Interacción registrada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


@company_emails_bp.route("/empresas/<int:cid>/interactions/delete/<int:iid>", methods=["POST"])
@login_required
def delete_interaction(cid, iid):
    intr = db.session.get(CompanyInteraction, iid)
    if intr and intr.company_id == cid:
        with sync_locked():
            db.session.delete(intr)
            db.session.commit()
            push_change_now("company_interactions", iid)
        flash("Interacción eliminada", "success")
    return redirect(url_for("companies.view", cid=cid))


# ═══════════════════════════════════════════
# n8n OUTBOX API (Bearer token)
# ═══════════════════════════════════════════

@company_emails_bp.route("/api/companies/outbox")
@api_token_required
def api_outbox():
    """Emails en cola esperando a ser enviados por n8n (últimos 10 min)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    q = (
        CompanyInteraction.query
        .options(joinedload(CompanyInteraction.company), joinedload(CompanyInteraction.contact))
        .filter(
            CompanyInteraction.type == "email",
            CompanyInteraction.status == "queued",
            CompanyInteraction.created_at >= cutoff,
        )
        .order_by(CompanyInteraction.created_at.asc())
    )
    out = []
    for i in q.all():
        if not i.to_email:
            continue
        out.append({
            "interaction_id": i.id,
            "company_id": i.company_id,
            "company_name": i.company.name if i.company else "",
            "contact_name": i.contact.name if i.contact else "",
            "to_email": i.to_email,
            "subject": i.subject,
            "body": i.body,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        })
    return jsonify({"data": out, "count": len(out)})


@company_emails_bp.route("/api/companies/mark-sent/<int:iid>", methods=["POST"])
@api_token_required
def api_mark_sent(iid):
    intr = db.session.get(CompanyInteraction, iid)
    if not intr or intr.type != "email":
        return jsonify({"error": "Interaction not found"}), 404
    intr.status = "sent"
    intr.sent_at = datetime.now(timezone.utc)
    db.session.commit()
    push_change("company_interactions", intr.id)
    return jsonify({"ok": True, "id": intr.id})


@company_emails_bp.route("/api/companies/due-reminders")
@api_token_required
def api_due_reminders():
    """
    Empresas en 'llamada_agendada' o 'interesado' sin interacción reciente (>= 3 días).
    n8n las notifica por Slack como recordatorio.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    statuses = ("llamada_agendada", "interesado", "negociacion")
    companies = Company.query.filter(Company.status.in_(statuses)).all()

    out = []
    for c in companies:
        last = (
            CompanyInteraction.query
            .filter_by(company_id=c.id)
            .order_by(CompanyInteraction.created_at.desc())
            .first()
        )
        if last and last.created_at and last.created_at >= cutoff:
            continue
        # contact principal: el primero con email/teléfono
        contacts = CompanyContact.query.filter_by(company_id=c.id).all()
        primary = next((ct for ct in contacts if ct.email or ct.phone), contacts[0] if contacts else None)
        out.append({
            "id": c.id,
            "empresa_name": c.name,
            "status": c.status,
            "contacto_nombre": primary.name if primary else "",
            "telefono": primary.phone if primary else "",
            "email": primary.email if primary else "",
            "last_interaction": last.created_at.isoformat() if last and last.created_at else None,
            "days_stale": (datetime.now(timezone.utc) - last.created_at).days if last and last.created_at else None,
        })
    return jsonify({"data": out, "count": len(out)})
