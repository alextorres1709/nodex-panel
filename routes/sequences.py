"""
Sequences (Apollo-style cadences) — listas ordenadas de pasos
(email automático, tarea de llamada, tarea manual, esperar N días).

Flujo:
  1. Usuario crea una Sequence con N pasos en /secuencias.
  2. Inscribe Leads (POST /secuencias/<sid>/enroll, lead_id=...).
     Esto crea un SequenceEnrollment con next_run_at = now + step.wait_days.
  3. n8n hace polling cada 15 min al endpoint
       GET  /api/sequences/due?limit=50
     Recibe enrollments listos para ejecutar (next_run_at <= now).
  4. Para cada uno:
       - Si el paso es "email"  → n8n envía email vía Gmail/SMTP, luego
         POST /api/sequences/enrollments/<eid>/advance (status=sent, message_id=...).
       - Si el paso es "call"   → n8n crea/actualiza una Task de llamada y
         POST /api/sequences/enrollments/<eid>/advance.
       - Si el paso es "wait"   → n8n simplemente avanza (advance) que
         calcula el siguiente next_run_at.
  5. Cuando current_step pasa del último paso → status=finished.
"""
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, g, jsonify,
)
from sqlalchemy.orm import joinedload

from models import (
    db, Sequence, SequenceStep, SequenceEnrollment, LeadInteraction,
    Lead, EmailTemplate, User, Task, TaskAssignment,
    SEQUENCE_STEP_TYPES, SEQUENCE_ENROLL_STATUSES,
)
from routes.auth import login_required, api_token_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

sequences_bp = Blueprint("sequences", __name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _render(text, lead, sender):
    """Reemplaza placeholders comunes en plantillas."""
    if not text:
        return ""
    company = (lead.company.name if lead.company else lead.company_name_cached) or ""
    contacto = (lead.first_name or lead.full_name or "").strip()
    return (
        text.replace("{empresa}", company)
            .replace("{contacto}", contacto)
            .replace("{nombre}", contacto)
            .replace("{nombre_completo}", lead.full_name or "")
            .replace("{nombre_remitente}", sender or "")
            .replace("{cargo}", lead.position or "")
    )


def _steps_ordered(seq):
    return list(seq.steps.order_by(SequenceStep.step_order.asc()).all())


def _schedule_next(enrollment, steps=None):
    """Calcula next_run_at + current_step. Cierra si ya no hay pasos."""
    steps = steps if steps is not None else _steps_ordered(enrollment.sequence)
    idx = enrollment.current_step
    if idx >= len(steps):
        enrollment.status = "finished"
        enrollment.finished_at = datetime.now(timezone.utc)
        enrollment.next_run_at = None
        return None
    step = steps[idx]
    delay = max(0, step.wait_days or 0)
    enrollment.next_run_at = datetime.now(timezone.utc) + timedelta(days=delay)
    return step


# ──────────────────────────────────────────────
# LISTA + DETALLE (CRUD secuencias)
# ──────────────────────────────────────────────

@sequences_bp.route("/secuencias")
@login_required
def index():
    sequences = (
        Sequence.query
        .options(joinedload(Sequence.creator))
        .order_by(Sequence.active.desc(), Sequence.created_at.desc())
        .all()
    )
    counts = {}
    for s in sequences:
        counts[s.id] = {
            "steps": s.steps.count(),
            "enrolled": SequenceEnrollment.query.filter_by(sequence_id=s.id, status="active").count(),
            "finished": SequenceEnrollment.query.filter_by(sequence_id=s.id, status="finished").count(),
        }
    return render_template(
        "secuencias.html",
        sequences=sequences,
        counts=counts,
    )


@sequences_bp.route("/secuencias/<int:sid>")
@login_required
def view(sid):
    seq = db.session.get(Sequence, sid)
    if not seq:
        abort(404)
    steps = _steps_ordered(seq)
    enrollments = (
        SequenceEnrollment.query
        .options(joinedload(SequenceEnrollment.lead), joinedload(SequenceEnrollment.enroller))
        .filter_by(sequence_id=sid)
        .order_by(SequenceEnrollment.created_at.desc())
        .all()
    )
    templates = (
        EmailTemplate.query
        .filter_by(active=True)
        .order_by(EmailTemplate.step_order.asc(), EmailTemplate.name.asc())
        .all()
    )
    return render_template(
        "secuencia_detail.html",
        sequence=seq,
        steps=steps,
        enrollments=enrollments,
        templates=templates,
        step_types=SEQUENCE_STEP_TYPES,
        enroll_statuses=SEQUENCE_ENROLL_STATUSES,
    )


@sequences_bp.route("/secuencias/create", methods=["POST"])
@login_required
def create():
    try:
        seq = Sequence(
            name=request.form.get("name", "").strip() or "Secuencia sin nombre",
            description=request.form.get("description", "").strip(),
            active=request.form.get("active", "on") == "on",
            created_by=g.user.id if g.get("user") else None,
        )
        db.session.add(seq)
        log_activity("create", "sequence", details=f"Secuencia: {seq.name}")
        db.session.commit()
        push_change("sequences", seq.id)
        flash("Secuencia creada", "success")
        return redirect(url_for("sequences.view", sid=seq.id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("sequences.index"))


@sequences_bp.route("/secuencias/edit/<int:sid>", methods=["POST"])
@login_required
def edit(sid):
    seq = db.session.get(Sequence, sid)
    if not seq:
        flash("Secuencia no encontrada", "error")
        return redirect(url_for("sequences.index"))
    try:
        seq.name = request.form.get("name", seq.name).strip()
        seq.description = request.form.get("description", "").strip()
        seq.active = request.form.get("active") == "on"
        db.session.commit()
        push_change("sequences", seq.id)
        flash("Secuencia actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("sequences.view", sid=sid))


@sequences_bp.route("/secuencias/delete/<int:sid>", methods=["POST"])
@login_required
def delete(sid):
    seq = db.session.get(Sequence, sid)
    if seq:
        sid_val = seq.id
        with sync_locked():
            log_activity("delete", "sequence", sid_val, f"Eliminada: {seq.name}")
            db.session.delete(seq)
            db.session.commit()
            push_change_now("sequences", sid_val)
        flash("Secuencia eliminada", "success")
    return redirect(url_for("sequences.index"))


# ──────────────────────────────────────────────
# STEPS (CRUD)
# ──────────────────────────────────────────────

@sequences_bp.route("/secuencias/<int:sid>/steps/create", methods=["POST"])
@login_required
def step_create(sid):
    seq = db.session.get(Sequence, sid)
    if not seq:
        abort(404)
    try:
        step_type = request.form.get("step_type", "email").strip()
        if step_type not in {k for k, _ in SEQUENCE_STEP_TYPES}:
            step_type = "email"
        wait_days = request.form.get("wait_days", "0").strip()
        order = request.form.get("step_order", "").strip()
        # Auto-calcula step_order si no viene
        if not order.isdigit():
            current_count = seq.steps.count()
            order = str(current_count + 1)
        tpl_id = request.form.get("template_id", "").strip()
        step = SequenceStep(
            sequence_id=seq.id,
            step_order=int(order),
            step_type=step_type,
            wait_days=int(wait_days) if wait_days.isdigit() else 0,
            template_id=int(tpl_id) if tpl_id else None,
            subject=request.form.get("subject", "").strip(),
            body=request.form.get("body", "").strip(),
            task_title=request.form.get("task_title", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(step)
        log_activity("create", "sequence_step", details=f"Paso {step.step_order} en {seq.name}")
        db.session.commit()
        push_change("sequence_steps", step.id)
        flash("Paso añadido", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("sequences.view", sid=sid))


@sequences_bp.route("/secuencias/<int:sid>/steps/edit/<int:stid>", methods=["POST"])
@login_required
def step_edit(sid, stid):
    step = db.session.get(SequenceStep, stid)
    if not step or step.sequence_id != sid:
        abort(404)
    try:
        step_type = request.form.get("step_type", step.step_type).strip()
        if step_type in {k for k, _ in SEQUENCE_STEP_TYPES}:
            step.step_type = step_type
        wait_days = request.form.get("wait_days", str(step.wait_days)).strip()
        if wait_days.isdigit():
            step.wait_days = int(wait_days)
        order = request.form.get("step_order", "").strip()
        if order.isdigit():
            step.step_order = int(order)
        tpl_id = request.form.get("template_id", "").strip()
        step.template_id = int(tpl_id) if tpl_id else None
        step.subject = request.form.get("subject", step.subject).strip()
        step.body = request.form.get("body", step.body).strip()
        step.task_title = request.form.get("task_title", step.task_title).strip()
        step.notes = request.form.get("notes", step.notes).strip()
        db.session.commit()
        push_change("sequence_steps", step.id)
        flash("Paso actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("sequences.view", sid=sid))


@sequences_bp.route("/secuencias/<int:sid>/steps/delete/<int:stid>", methods=["POST"])
@login_required
def step_delete(sid, stid):
    step = db.session.get(SequenceStep, stid)
    if step and step.sequence_id == sid:
        stid_val = step.id
        with sync_locked():
            db.session.delete(step)
            db.session.commit()
            push_change_now("sequence_steps", stid_val)
        flash("Paso eliminado", "success")
    return redirect(url_for("sequences.view", sid=sid))


# ──────────────────────────────────────────────
# ENROLLMENT (inscribir leads)
# ──────────────────────────────────────────────

@sequences_bp.route("/secuencias/<int:sid>/enroll", methods=["POST"])
@login_required
def enroll(sid):
    seq = db.session.get(Sequence, sid)
    if not seq:
        abort(404)
    if not seq.active:
        flash("Secuencia inactiva", "error")
        return redirect(url_for("sequences.view", sid=sid))

    raw_ids = request.form.getlist("lead_ids") or [request.form.get("lead_id", "")]
    ids = []
    for v in raw_ids:
        v = (v or "").strip()
        if not v:
            continue
        # Acepta CSV (varios IDs separados por coma)
        for part in v.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
    ids = list(dict.fromkeys(ids))

    if not ids:
        flash("Selecciona al menos un lead", "error")
        return redirect(request.form.get("next") or url_for("sequences.view", sid=sid))

    steps = _steps_ordered(seq)
    if not steps:
        flash("La secuencia no tiene pasos", "error")
        return redirect(url_for("sequences.view", sid=sid))

    added, skipped = 0, 0
    for lid in ids:
        lead = db.session.get(Lead, lid)
        if not lead:
            continue
        # Evita duplicar enrollment activo
        existing = (
            SequenceEnrollment.query
            .filter_by(sequence_id=sid, lead_id=lid)
            .filter(SequenceEnrollment.status.in_(("active", "paused")))
            .first()
        )
        if existing:
            skipped += 1
            continue
        e = SequenceEnrollment(
            sequence_id=sid,
            lead_id=lid,
            current_step=0,
            status="active",
            enrolled_by=g.user.id if g.get("user") else None,
        )
        db.session.add(e)
        db.session.flush()
        _schedule_next(e, steps=steps)
        added += 1

    log_activity("enroll", "sequence", sid, f"+{added} leads en {seq.name}")
    db.session.commit()
    push_change("sequences", sid)
    flash(f"Inscritos: {added} (omitidos por duplicado: {skipped})", "success")
    return redirect(request.form.get("next") or url_for("sequences.view", sid=sid))


@sequences_bp.route("/secuencias/enrollments/<int:eid>/pause", methods=["POST"])
@login_required
def enrollment_pause(eid):
    e = db.session.get(SequenceEnrollment, eid)
    if e:
        e.status = "paused"
        db.session.commit()
        push_change("sequence_enrollments", e.id)
    return redirect(request.referrer or url_for("sequences.index"))


@sequences_bp.route("/secuencias/enrollments/<int:eid>/resume", methods=["POST"])
@login_required
def enrollment_resume(eid):
    e = db.session.get(SequenceEnrollment, eid)
    if e and e.status in ("paused", "cancelled"):
        e.status = "active"
        if not e.next_run_at:
            _schedule_next(e)
        db.session.commit()
        push_change("sequence_enrollments", e.id)
    return redirect(request.referrer or url_for("sequences.index"))


@sequences_bp.route("/secuencias/enrollments/<int:eid>/cancel", methods=["POST"])
@login_required
def enrollment_cancel(eid):
    e = db.session.get(SequenceEnrollment, eid)
    if e:
        e.status = "cancelled"
        e.next_run_at = None
        db.session.commit()
        push_change("sequence_enrollments", e.id)
    return redirect(request.referrer or url_for("sequences.index"))


# ──────────────────────────────────────────────
# n8n SCHEDULER API (Bearer token)
# ──────────────────────────────────────────────

@sequences_bp.route("/api/sequences/due")
@api_token_required
def api_due():
    """Enrollments listos para ejecutar (next_run_at <= now, status=active)."""
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))

    now = datetime.now(timezone.utc)
    rows = (
        SequenceEnrollment.query
        .options(
            joinedload(SequenceEnrollment.lead).joinedload(Lead.company),
            joinedload(SequenceEnrollment.sequence),
        )
        .filter(SequenceEnrollment.status == "active")
        .filter(SequenceEnrollment.next_run_at != None)  # noqa: E711
        .filter(SequenceEnrollment.next_run_at <= now)
        .order_by(SequenceEnrollment.next_run_at.asc())
        .limit(limit)
        .all()
    )

    out = []
    for e in rows:
        lead = e.lead
        if not lead:
            continue
        steps = _steps_ordered(e.sequence)
        idx = e.current_step
        if idx >= len(steps):
            # Edge case: sin pasos restantes — finaliza y salta
            e.status = "finished"
            e.finished_at = now
            e.next_run_at = None
            continue
        step = steps[idx]

        sender_name = ""  # n8n puede sobreescribir si quiere
        rendered_subject = _render(step.subject or (step.template.subject if step.template else ""), lead, sender_name)
        rendered_body = _render(step.body or (step.template.body if step.template else ""), lead, sender_name)

        out.append({
            "enrollment_id": e.id,
            "sequence_id": e.sequence_id,
            "sequence_name": e.sequence.name if e.sequence else "",
            "lead_id": lead.id,
            "lead_name": lead.full_name,
            "lead_email": lead.email or "",
            "lead_phone": lead.phone or "",
            "company_name": (lead.company.name if lead.company else lead.company_name_cached) or "",
            "step_id": step.id,
            "step_order": step.step_order,
            "step_type": step.step_type,
            "wait_days": step.wait_days or 0,
            "subject": rendered_subject,
            "body": rendered_body,
            "task_title": step.task_title or "",
            "template_id": step.template_id,
            "next_run_at": e.next_run_at.isoformat() if e.next_run_at else None,
        })

    db.session.commit()  # commit edge-case finishes
    return jsonify({"data": out, "count": len(out)})


@sequences_bp.route("/api/sequences/enrollments/<int:eid>/advance", methods=["POST"])
@api_token_required
def api_advance(eid):
    """Llamado por n8n tras ejecutar un paso. Avanza el current_step.

    Body JSON o form (todos opcionales):
      step_status: sent|done|failed   (default: done)
      message_id : id externo (msgid de Gmail, etc.)
      error      : detalle si falló
      log_subject/log_body: override para LeadInteraction
    """
    e = db.session.get(SequenceEnrollment, eid)
    if not e:
        return jsonify({"error": "enrollment_not_found"}), 404

    payload = request.get_json(silent=True) or request.form
    step_status = (payload.get("step_status") or "done").strip()
    message_id = (payload.get("message_id") or "").strip()
    error = (payload.get("error") or "").strip()

    seq = e.sequence
    if not seq:
        return jsonify({"error": "sequence_missing"}), 500
    steps = _steps_ordered(seq)
    if e.current_step >= len(steps):
        e.status = "finished"
        e.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"ok": True, "status": "finished"})
    step = steps[e.current_step]

    # Loggea la interacción
    intr_type = "email" if step.step_type == "email" else (
        "call" if step.step_type == "call" else "note"
    )
    intr = LeadInteraction(
        lead_id=e.lead_id,
        enrollment_id=e.id,
        step_id=step.id,
        type=intr_type,
        status="sent" if step_status == "sent" else ("failed" if step_status == "failed" else "done"),
        subject=(payload.get("log_subject") or step.subject or step.task_title or "")[:300],
        body=(payload.get("log_body") or (error if step_status == "failed" else (step.body or step.notes or ""))),
        to_email=(e.lead.email if e.lead else "") or "",
        template_id=step.template_id,
        sent_at=datetime.now(timezone.utc) if step_status == "sent" else None,
    )
    db.session.add(intr)
    if message_id:
        intr.subject = (intr.subject + f" [msg:{message_id[:80]}]")[:300]

    # Si el paso es "call"/"manual" y aún no hay tarea ligada, créala
    if step.step_type in ("call", "manual") and step_status != "failed":
        title = step.task_title or (
            f"Llamar a {e.lead.full_name}" if step.step_type == "call"
            else f"Acción para {e.lead.full_name}"
        )
        existing_task = Task.query.filter_by(title=title).filter(Task.status != "completada").first()
        if not existing_task:
            t = Task(
                title=title,
                description=f"Auto-creada desde secuencia '{seq.name}', paso {step.step_order}.",
                priority=e.lead.priority if e.lead else "media",
                status="pendiente",
                company_id=e.lead.company_id if e.lead else None,
            )
            db.session.add(t)
            db.session.flush()
            if e.lead and e.lead.assigned_to:
                db.session.add(TaskAssignment(task_id=t.id, user_id=e.lead.assigned_to))

    e.last_step_at = datetime.now(timezone.utc)
    if step_status == "failed":
        # No avanzamos: pausamos y dejamos al usuario decidir
        e.status = "paused"
        db.session.commit()
        push_change("sequence_enrollments", e.id)
        return jsonify({"ok": True, "status": "paused", "reason": "step_failed"})

    e.current_step += 1
    _schedule_next(e, steps=steps)
    db.session.commit()
    push_change("sequence_enrollments", e.id)
    return jsonify({
        "ok": True,
        "status": e.status,
        "current_step": e.current_step,
        "next_run_at": e.next_run_at.isoformat() if e.next_run_at else None,
    })
