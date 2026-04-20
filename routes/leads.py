"""
Leads — sección estilo Apollo.io.

Cada Lead es una persona/contacto comercial:
  - Puede pertenecer a una Company (Empresa a contactar) ya existente.
  - Puede inscribirse en Secuencias (Sequence) que disparan emails y tareas
    de llamada vía n8n.
  - Cuando avanza a status="cliente" reemplaza al antiguo modelo Client
    (la sección "Clientes" del nav desaparece).
"""
from datetime import datetime, date, timezone
from io import StringIO
import csv

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, g, Response, jsonify,
)
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func

from models import (
    db, Lead, LeadInteraction, Company,
    Sequence, SequenceEnrollment, EmailTemplate, User, Task, TaskAssignment,
    Project,
)
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

leads_bp = Blueprint("leads", __name__)


# ──────────────────────────────────────────────
# CONSTANTES + helpers
# ──────────────────────────────────────────────

_PRIORITY_RANK = {"alta": 0, "media": 1, "baja": 2}

# Pipeline visual (orden + label) — usado en kanban y filtros
PIPELINE = [
    ("nuevo",        "Nuevo",        "#64748b"),
    ("contactado",   "Contactado",   "#0ea5e9"),
    ("interesado",   "Interesado",   "#8b5cf6"),
    ("qualified",    "Cualificado",  "#a855f7"),
    ("propuesta",    "Propuesta",    "#f59e0b"),
    ("negociacion",  "Negociación",  "#f97316"),
    ("cliente",      "Cliente",      "#22c55e"),
    ("perdido",      "Perdido",      "#ef4444"),
]
PIPELINE_KEYS = [k for k, _, _ in PIPELINE]
PIPELINE_LABELS = {k: lbl for k, lbl, _ in PIPELINE}
PIPELINE_COLORS = {k: c for k, _, c in PIPELINE}


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s.split("T")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _ensure_followup_task(lead, prev_date):
    """Si next_contact_date cambia → crea/actualiza una Task ligada al lead.

    Idempotente: si ya existe una pendiente con el mismo título/fecha, no duplica.
    """
    new_date = lead.next_contact_date
    if not new_date or new_date == prev_date:
        return None
    title = f"Llamar a {lead.full_name}"
    existing = (
        Task.query
        .filter_by(title=title, due_date=new_date)
        .filter(Task.status != "completada")
        .first()
    )
    if existing:
        return existing
    t = Task(
        title=title,
        description=(
            f"Auto-creada desde 'Próximo contacto' del lead {lead.full_name}"
            f"{(' (' + lead.display_company + ')') if lead.display_company else ''}."
        ),
        priority=lead.priority or "media",
        status="pendiente",
        due_date=new_date,
        company_id=lead.company_id,
    )
    db.session.add(t)
    db.session.flush()
    if lead.assigned_to:
        db.session.add(TaskAssignment(task_id=t.id, user_id=lead.assigned_to))
    return t


def _record_status_change(lead, old, new, reason=""):
    """Registra cambios de status como LeadInteraction tipo status_change."""
    if old == new:
        return
    body = f"{old or '?'} → {new}"
    if reason:
        body += f" — {reason}"
    db.session.add(LeadInteraction(
        lead_id=lead.id,
        user_id=g.user.id if g.get("user") else None,
        type="status_change",
        status="done",
        subject=f"Cambio de status",
        body=body,
    ))
    if new == "cliente" and not lead.converted_at:
        lead.converted_at = datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# LIST + Kanban
# ──────────────────────────────────────────────

@leads_bp.route("/leads")
@login_required
def index():
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    assigned = request.args.get("assigned", "").strip()
    company_id = request.args.get("company_id", "").strip()
    sequence_id = request.args.get("sequence_id", "").strip()
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "priority")  # priority, next_contact, recent, name

    q = Lead.query.options(
        joinedload(Lead.company),
        joinedload(Lead.assignee),
    )
    if status:
        q = q.filter(Lead.status == status)
    if priority:
        q = q.filter(Lead.priority == priority)
    if assigned:
        try:
            q = q.filter(Lead.assigned_to == int(assigned))
        except ValueError:
            pass
    if company_id:
        try:
            q = q.filter(Lead.company_id == int(company_id))
        except ValueError:
            pass
    if sequence_id:
        try:
            sub = (
                db.session.query(SequenceEnrollment.lead_id)
                .filter(SequenceEnrollment.sequence_id == int(sequence_id))
            )
            q = q.filter(Lead.id.in_(sub))
        except ValueError:
            pass
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Lead.first_name.ilike(like),
            Lead.last_name.ilike(like),
            Lead.email.ilike(like),
            Lead.phone.ilike(like),
            Lead.position.ilike(like),
            Lead.company_name_cached.ilike(like),
        ))

    leads = q.all()

    today = date.today()

    def _key(l):
        prio = _PRIORITY_RANK.get(l.priority or "media", 1)
        nxt = l.next_contact_date or date.max
        days = (nxt - today).days if l.next_contact_date else 9999
        if sort == "next_contact":
            return (nxt, prio, -(l.id or 0))
        if sort == "recent":
            return (-(l.created_at.timestamp() if l.created_at else 0),)
        if sort == "name":
            return ((l.full_name or "").lower(),)
        return (prio, days, -(l.id or 0))
    leads.sort(key=_key)

    # Active enrollments per lead (id → list of (seq_name, status))
    enroll_by_lead = {}
    enrolls = (
        SequenceEnrollment.query
        .options(joinedload(SequenceEnrollment.sequence))
        .filter(SequenceEnrollment.lead_id.in_([l.id for l in leads] or [0]))
        .all()
    )
    for e in enrolls:
        enroll_by_lead.setdefault(e.lead_id, []).append(e)

    users = User.query.filter_by(active=True).order_by(User.name.asc()).all()
    companies = Company.query.order_by(Company.name.asc()).all()
    sequences = Sequence.query.filter_by(active=True).order_by(Sequence.name.asc()).all()

    # KPIs
    kpi = {
        "total": len(leads),
        "by_status": {k: 0 for k, _, _ in PIPELINE},
        "alta": 0,
        "overdue": 0,
        "this_week": 0,
    }
    for l in leads:
        kpi["by_status"][l.status or "nuevo"] = kpi["by_status"].get(l.status or "nuevo", 0) + 1
        if (l.priority or "media") == "alta":
            kpi["alta"] += 1
        if l.next_contact_date and l.next_contact_date < today:
            kpi["overdue"] += 1
        if l.next_contact_date and 0 <= (l.next_contact_date - today).days <= 7:
            kpi["this_week"] += 1

    return render_template(
        "leads.html",
        leads=leads,
        sel_status=status,
        sel_priority=priority,
        sel_assigned=assigned,
        sel_company=company_id,
        sel_sequence=sequence_id,
        sel_sort=sort,
        search=search,
        users=users,
        companies=companies,
        sequences=sequences,
        pipeline=PIPELINE,
        pipeline_labels=PIPELINE_LABELS,
        pipeline_colors=PIPELINE_COLORS,
        enroll_by_lead=enroll_by_lead,
        kpi=kpi,
        today=today,
    )


# ──────────────────────────────────────────────
# DETAIL (drawer/page)
# ──────────────────────────────────────────────

@leads_bp.route("/leads/<int:lid>")
@login_required
def view(lid):
    lead = (
        Lead.query
        .options(joinedload(Lead.company), joinedload(Lead.assignee))
        .filter(Lead.id == lid)
        .first()
    )
    if not lead:
        abort(404)

    interactions = (
        LeadInteraction.query
        .options(joinedload(LeadInteraction.user), joinedload(LeadInteraction.template))
        .filter_by(lead_id=lid)
        .order_by(LeadInteraction.created_at.desc())
        .all()
    )
    enrollments = (
        SequenceEnrollment.query
        .options(joinedload(SequenceEnrollment.sequence), joinedload(SequenceEnrollment.enroller))
        .filter_by(lead_id=lid)
        .order_by(SequenceEnrollment.created_at.desc())
        .all()
    )
    projects = (
        Project.query
        .filter_by(lead_id=lid)
        .order_by(Project.created_at.desc())
        .all()
    )
    if lead.company_id:
        tasks = (
            Task.query
            .filter(Task.company_id == lead.company_id)
            .order_by(Task.created_at.desc())
            .limit(20)
            .all()
        )
    else:
        tasks = []

    users = User.query.filter_by(active=True).order_by(User.name.asc()).all()
    companies = Company.query.order_by(Company.name.asc()).all()
    sequences = Sequence.query.filter_by(active=True).order_by(Sequence.name.asc()).all()
    templates = EmailTemplate.query.filter_by(active=True).order_by(EmailTemplate.step_order.asc()).all()

    return render_template(
        "lead_detail.html",
        lead=lead,
        interactions=interactions,
        enrollments=enrollments,
        projects=projects,
        tasks=tasks,
        users=users,
        companies=companies,
        sequences=sequences,
        templates=templates,
        pipeline=PIPELINE,
        pipeline_labels=PIPELINE_LABELS,
        pipeline_colors=PIPELINE_COLORS,
    )


# ──────────────────────────────────────────────
# CREATE / EDIT / DELETE
# ──────────────────────────────────────────────

def _form_to_lead_kwargs(form, existing=None):
    company_id = form.get("company_id", "").strip()
    assigned = form.get("assigned_to", "").strip()
    return dict(
        first_name=form.get("first_name", "").strip(),
        last_name=form.get("last_name", "").strip(),
        email=form.get("email", "").strip(),
        phone=form.get("phone", "").strip(),
        position=form.get("position", "").strip(),
        linkedin=form.get("linkedin", "").strip(),
        company_id=int(company_id) if company_id else None,
        company_name_cached=form.get("company_name", "").strip(),
        status=form.get("status", existing.status if existing else "nuevo"),
        priority=form.get("priority", existing.priority if existing else "media"),
        source=form.get("source", "").strip(),
        assigned_to=int(assigned) if assigned else None,
        next_contact_date=_parse_date(form.get("next_contact_date")),
        notes=form.get("notes", "").strip(),
        tags=form.get("tags", "").strip(),
    )


@leads_bp.route("/leads/create", methods=["POST"])
@login_required
def create():
    try:
        kw = _form_to_lead_kwargs(request.form)
        # Cache company name si se eligió company_id
        if kw["company_id"] and not kw["company_name_cached"]:
            comp = db.session.get(Company, kw["company_id"])
            if comp:
                kw["company_name_cached"] = comp.name

        lead = Lead(**kw)
        db.session.add(lead)
        db.session.flush()

        if lead.next_contact_date:
            _ensure_followup_task(lead, prev_date=None)

        log_activity("create", "lead", lead.id, f"Nuevo lead: {lead.full_name}")
        db.session.commit()
        push_change("leads", lead.id)
        flash("Lead creado", "success")
        if request.form.get("redirect_to_detail"):
            return redirect(url_for("leads.view", lid=lead.id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("leads.index"))


@leads_bp.route("/leads/edit/<int:lid>", methods=["POST"])
@login_required
def edit(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        flash("Lead no encontrado", "error")
        return redirect(url_for("leads.index"))
    try:
        prev_date = lead.next_contact_date
        prev_status = lead.status
        kw = _form_to_lead_kwargs(request.form, existing=lead)
        for k, v in kw.items():
            setattr(lead, k, v)
        # Cache company name si se eligió company_id
        if lead.company_id and not lead.company_name_cached:
            comp = db.session.get(Company, lead.company_id)
            if comp:
                lead.company_name_cached = comp.name

        if lead.next_contact_date and lead.next_contact_date != prev_date:
            _ensure_followup_task(lead, prev_date=prev_date)
        if lead.status != prev_status:
            _record_status_change(lead, prev_status, lead.status, request.form.get("status_reason", ""))

        log_activity("update", "lead", lead.id, f"Editado: {lead.full_name}")
        db.session.commit()
        push_change("leads", lead.id)
        flash("Lead actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(request.form.get("next") or url_for("leads.view", lid=lid))


@leads_bp.route("/leads/delete/<int:lid>", methods=["POST"])
@login_required
def delete(lid):
    lead = db.session.get(Lead, lid)
    if lead:
        with sync_locked():
            log_activity("delete", "lead", lead.id, f"Eliminado: {lead.full_name}")
            db.session.delete(lead)
            db.session.commit()
            push_change_now("leads", lid)
        flash("Lead eliminado", "success")
    return redirect(url_for("leads.index"))


# ──────────────────────────────────────────────
# QUICK INLINE EDITS (drawer + tabla densa)
# ──────────────────────────────────────────────

@leads_bp.route("/leads/<int:lid>/quick-status", methods=["POST"])
@login_required
def quick_status(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    new = (request.form.get("status") or "").strip()
    if new not in PIPELINE_KEYS:
        return jsonify({"error": "invalid_status"}), 400
    old = lead.status
    lead.status = new
    _record_status_change(lead, old, new)
    db.session.commit()
    push_change("leads", lead.id)
    return jsonify({"ok": True, "status": new, "label": PIPELINE_LABELS.get(new, new)})


@leads_bp.route("/leads/<int:lid>/quick-priority", methods=["POST"])
@login_required
def quick_priority(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    new = (request.form.get("priority") or "media").strip()
    if new not in ("alta", "media", "baja"):
        return jsonify({"error": "invalid"}), 400
    lead.priority = new
    db.session.commit()
    push_change("leads", lead.id)
    return jsonify({"ok": True, "priority": new})


@leads_bp.route("/leads/<int:lid>/quick-next-contact", methods=["POST"])
@login_required
def quick_next_contact(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    prev = lead.next_contact_date
    lead.next_contact_date = _parse_date(request.form.get("next_contact_date"))
    if lead.next_contact_date:
        _ensure_followup_task(lead, prev_date=prev)
    db.session.commit()
    push_change("leads", lead.id)
    return jsonify({
        "ok": True,
        "next_contact_date": lead.next_contact_date.isoformat() if lead.next_contact_date else None,
    })


@leads_bp.route("/leads/<int:lid>/quick-assigned", methods=["POST"])
@login_required
def quick_assigned(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    val = (request.form.get("assigned_to") or "").strip()
    lead.assigned_to = int(val) if val else None
    db.session.commit()
    push_change("leads", lead.id)
    return jsonify({"ok": True, "assigned_to": lead.assigned_to})


# ──────────────────────────────────────────────
# CONVERSIÓN: Lead → Cliente / pasar entre estados clave
# ──────────────────────────────────────────────

@leads_bp.route("/leads/<int:lid>/convert-client", methods=["POST"])
@login_required
def convert_client(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        flash("Lead no encontrado", "error")
        return redirect(url_for("leads.index"))
    old = lead.status
    lead.status = "cliente"
    _record_status_change(lead, old, "cliente", "Convertido manualmente a cliente")
    log_activity("convert", "lead", lead.id, f"Lead → Cliente: {lead.full_name}")
    db.session.commit()
    push_change("leads", lead.id)
    flash(f"{lead.full_name} ahora es Cliente", "success")
    return redirect(request.form.get("next") or url_for("leads.view", lid=lid))


@leads_bp.route("/leads/<int:lid>/mark-lost", methods=["POST"])
@login_required
def mark_lost(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        return redirect(url_for("leads.index"))
    old = lead.status
    lead.status = "perdido"
    lead.lost_reason = request.form.get("lost_reason", "").strip()
    _record_status_change(lead, old, "perdido", lead.lost_reason)
    log_activity("lost", "lead", lead.id, f"Marcado perdido: {lead.full_name}")
    db.session.commit()
    push_change("leads", lead.id)
    flash("Lead marcado como perdido", "success")
    return redirect(request.form.get("next") or url_for("leads.view", lid=lid))


# ──────────────────────────────────────────────
# INTERACTIONS (timeline manual: notas/llamadas/reuniones)
# ──────────────────────────────────────────────

@leads_bp.route("/leads/<int:lid>/interactions/log", methods=["POST"])
@login_required
def log_interaction(lid):
    lead = db.session.get(Lead, lid)
    if not lead:
        abort(404)
    try:
        itype = request.form.get("type", "note").strip()
        if itype not in ("call", "meeting", "note"):
            flash("Tipo inválido", "error")
            return redirect(url_for("leads.view", lid=lid))
        body = request.form.get("body", "").strip()
        subject = request.form.get("subject", "").strip() or {
            "call": "Llamada registrada",
            "meeting": "Reunión registrada",
            "note": "Nota",
        }[itype]
        intr = LeadInteraction(
            lead_id=lid,
            user_id=g.user.id if g.get("user") else None,
            type=itype,
            status="done",
            subject=subject,
            body=body,
        )
        db.session.add(intr)
        # Auto-advance: primera llamada/reunión → "interesado"
        if itype in ("call", "meeting") and lead.status in ("nuevo", "contactado"):
            old = lead.status
            lead.status = "interesado"
            _record_status_change(lead, old, "interesado", "Auto-avance tras interacción")
        log_activity(f"log_{itype}", "lead", lid, subject)
        db.session.commit()
        push_change("lead_interactions", intr.id)
        push_change("leads", lid)
        flash("Interacción registrada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("leads.view", lid=lid))


@leads_bp.route("/leads/<int:lid>/interactions/delete/<int:iid>", methods=["POST"])
@login_required
def delete_interaction(lid, iid):
    intr = db.session.get(LeadInteraction, iid)
    if intr and intr.lead_id == lid:
        with sync_locked():
            db.session.delete(intr)
            db.session.commit()
            push_change_now("lead_interactions", iid)
        flash("Interacción eliminada", "success")
    return redirect(url_for("leads.view", lid=lid))


# ──────────────────────────────────────────────
# IMPORT / EXPORT CSV
# ──────────────────────────────────────────────

CSV_COLS = [
    "first_name", "last_name", "email", "phone", "position", "linkedin",
    "company_name", "status", "priority", "source", "next_contact_date",
    "tags", "notes",
]

# Aliases ES → field
ALIASES = {
    "nombre": "first_name", "apellido": "last_name", "apellidos": "last_name",
    "correo": "email", "telefono": "phone", "tel": "phone", "movil": "phone",
    "puesto": "position", "cargo": "position", "rol": "position",
    "linkedin": "linkedin",
    "empresa": "company_name", "compania": "company_name", "company": "company_name",
    "estado": "status", "prioridad": "priority",
    "origen": "source", "fuente": "source",
    "proximo_contacto": "next_contact_date", "next_contact": "next_contact_date",
    "etiquetas": "tags", "tags": "tags",
    "notas": "notes", "notes": "notes",
}


@leads_bp.route("/leads/export.csv")
@login_required
def export_csv():
    leads = Lead.query.options(joinedload(Lead.company)).order_by(Lead.created_at.desc()).all()
    out = StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLS)
    for l in leads:
        w.writerow([
            l.first_name or "",
            l.last_name or "",
            l.email or "",
            l.phone or "",
            l.position or "",
            l.linkedin or "",
            (l.company.name if l.company else l.company_name_cached) or "",
            l.status or "",
            l.priority or "",
            l.source or "",
            l.next_contact_date.isoformat() if l.next_contact_date else "",
            l.tags or "",
            (l.notes or "").replace("\n", " "),
        ])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@leads_bp.route("/leads/import", methods=["POST"])
@login_required
def import_csv():
    f = request.files.get("csv_file")
    if not f:
        flash("Selecciona un archivo CSV", "error")
        return redirect(url_for("leads.index"))
    try:
        raw = f.read().decode("utf-8-sig", errors="ignore")
        sample = raw[:2000]
        # Detectar delimitador
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delim = dialect.delimiter
        except Exception:
            delim = ";" if sample.count(";") > sample.count(",") else ","

        reader = csv.DictReader(StringIO(raw), delimiter=delim)
        # Normalize header names
        normalized_fields = {}
        for fld in (reader.fieldnames or []):
            key = (fld or "").strip().lower().replace(" ", "_")
            if key in CSV_COLS:
                normalized_fields[fld] = key
            elif key in ALIASES:
                normalized_fields[fld] = ALIASES[key]

        created, updated, skipped = 0, 0, 0
        for row in reader:
            data = {}
            for orig, mapped in normalized_fields.items():
                data[mapped] = (row.get(orig) or "").strip()

            email = (data.get("email") or "").strip().lower()
            first = (data.get("first_name") or "").strip()
            last = (data.get("last_name") or "").strip()
            company_name = (data.get("company_name") or "").strip()

            if not (email or first or last):
                skipped += 1
                continue

            # Find existing lead by email (preferred) or full_name+company
            existing = None
            if email:
                existing = Lead.query.filter(func.lower(Lead.email) == email).first()
            if not existing and (first or last) and company_name:
                existing = (
                    Lead.query
                    .filter(Lead.first_name == first, Lead.last_name == last)
                    .filter(or_(
                        Lead.company_name_cached == company_name,
                        Lead.company.has(Company.name == company_name),
                    ))
                    .first()
                )

            # Find or attach to company
            company_id = None
            if company_name:
                comp = Company.query.filter(func.lower(Company.name) == company_name.lower()).first()
                if comp:
                    company_id = comp.id

            payload = {
                "first_name": first,
                "last_name": last,
                "email": email,
                "phone": data.get("phone", ""),
                "position": data.get("position", ""),
                "linkedin": data.get("linkedin", ""),
                "company_id": company_id,
                "company_name_cached": company_name,
                "status": (data.get("status") or "nuevo").lower() if (data.get("status") or "").lower() in PIPELINE_KEYS else "nuevo",
                "priority": (data.get("priority") or "media").lower() if (data.get("priority") or "").lower() in ("alta", "media", "baja") else "media",
                "source": data.get("source", "") or "csv",
                "next_contact_date": _parse_date(data.get("next_contact_date")),
                "tags": data.get("tags", ""),
                "notes": data.get("notes", ""),
            }

            if existing:
                for k, v in payload.items():
                    if v not in (None, ""):
                        setattr(existing, k, v)
                updated += 1
            else:
                db.session.add(Lead(**payload))
                created += 1

        db.session.commit()
        flash(f"Importado: {created} nuevos, {updated} actualizados, {skipped} omitidos", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error importando: {e}", "error")
    return redirect(url_for("leads.index"))
