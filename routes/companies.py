from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g, Response, jsonify
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from models import db, Company, CompanyContact, Project, Task, TaskAssignment, User, Idea, CompanyInteraction, EmailTemplate, Lead, CompanyAssignment
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

companies_bp = Blueprint("companies", __name__)


# Priority sort: alta=0, media=1, baja=2 (alta first)
_PRIORITY_RANK = {"alta": 0, "media": 1, "baja": 2}


def _parse_date(s):
    """Parse YYYY-MM-DD or empty → None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s.split("T")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _ensure_followup_task(company, prev_date):
    """When next_contact_date changes, create a linked follow-up Task.

    Idempotent — if a pending task already exists for this company with the
    same due_date and the auto-generated title, do nothing.
    """
    new_date = company.next_contact_date
    if not new_date or new_date == prev_date:
        return None
    title = f"Contactar {company.name}"
    existing = (
        Task.query
        .filter_by(company_id=company.id, title=title, due_date=new_date)
        .filter(Task.status != "completada")
        .first()
    )
    if existing:
        return existing
    t = Task(
        title=title,
        description=f"Auto-creada desde 'Próximo contacto' de {company.name}.",
        priority=company.priority or "media",
        status="pendiente",
        due_date=new_date,
        company_id=company.id,
    )
    db.session.add(t)
    db.session.flush()
    assigned_user_ids = [a.user_id for a in CompanyAssignment.query.filter_by(company_id=company.id).all()]
    if not assigned_user_ids and company.assigned_to:
        assigned_user_ids = [company.assigned_to]
    for uid in assigned_user_ids:
        db.session.add(TaskAssignment(task_id=t.id, user_id=uid))
    return t

def _sync_assignees_to_leads(company):
    assigned_ids = [a.user_id for a in CompanyAssignment.query.filter_by(company_id=company.id).all()]
    from models import LeadAssignment
    leads = Lead.query.filter_by(company_id=company.id).all()
    for lead in leads:
        LeadAssignment.query.filter_by(lead_id=lead.id).delete()
        for uid in assigned_ids:
            db.session.add(LeadAssignment(lead_id=lead.id, user_id=uid))
        lead.assigned_to = company.assigned_to


@companies_bp.route("/empresas")
@login_required
def index():
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")
    assigned = request.args.get("assigned", "")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "priority")  # priority, next_contact, recent, name
    view_mode = request.args.get("view", "list")  # list, kanban

    q = Company.query
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if assigned:
        try:
            q = q.filter(or_(Company.assigned_to == int(assigned), Company.assignees.any(User.id == int(assigned))))
        except ValueError:
            pass
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Company.name.ilike(like),
            Company.industry.ilike(like),
            Company.website.ilike(like),
            Company.email.ilike(like),
            Company.phone.ilike(like),
        ))

    companies = q.all()

    # Sort in Python so we can use the priority rank map (alta > media > baja)
    today = date.today()
    def _sort_key(c):
        prio = _PRIORITY_RANK.get(c.priority or "media", 1)
        nxt = c.next_contact_date or date.max
        days_until = (nxt - today).days if c.next_contact_date else 9999
        if sort == "next_contact":
            return (nxt, prio, -(c.id or 0))
        if sort == "recent":
            return (-(c.created_at.timestamp() if c.created_at else 0),)
        if sort == "name":
            return ((c.name or "").lower(),)
        # Default: priority — alta first, then nearest next_contact, then recent
        return (prio, days_until, -(c.id or 0))
    companies.sort(key=_sort_key)

    # Count contacts per company
    contact_counts = {}
    for c in companies:
        contact_counts[c.id] = CompanyContact.query.filter_by(company_id=c.id).count()

    users = User.query.filter_by(active=True).order_by(User.name.asc()).all()

    # For Kanban: group by status
    kanban_columns = []
    if view_mode == "kanban":
        STATUS_ORDER = [
            ("por_escribir", "Por escribir"),
            ("contactada_sin_respuesta", "Sin respuesta"),
            ("interesado", "Interesado"),
            ("llamada_agendada", "Llamada agendada"),
            ("demo_preparacion", "Demo (prep.)"),
            ("demo_realizada", "Demo realizada"),
            ("propuesta_enviada", "Propuesta enviada"),
            ("negociacion", "Negociación"),
            ("cerrado_ganado", "Ganado"),
            ("cerrado_perdido", "Perdido"),
        ]
        by_status = {}
        for c in companies:
            by_status.setdefault(c.status or "por_escribir", []).append(c)
        kanban_columns = [(key, label, by_status.get(key, [])) for key, label in STATUS_ORDER]

    return render_template("empresas.html", companies=companies,
                           contact_counts=contact_counts, sel_status=status,
                           sel_priority=priority, sel_assigned=assigned,
                           sel_sort=sort, view_mode=view_mode, search=search,
                           users=users, kanban_columns=kanban_columns,
                           today=today)


@companies_bp.route("/empresas/<int:cid>")
@login_required
def view(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)

    contacts = CompanyContact.query.filter_by(company_id=cid).order_by(CompanyContact.created_at.desc()).all()
    tasks = Task.query.options(
        joinedload(Task.assignee)
    ).filter_by(company_id=cid).order_by(Task.created_at.desc()).all()
    task_counts = {
        "pendiente": sum(1 for t in tasks if t.status == "pendiente"),
        "en_progreso": sum(1 for t in tasks if t.status == "en_progreso"),
        "en_espera": sum(1 for t in tasks if t.status == "en_espera"),
        "completada": sum(1 for t in tasks if t.status == "completada"),
    }
    ideas = Idea.query.filter_by(company_id=cid).order_by(Idea.votes.desc(), Idea.created_at.desc()).all()
    projects = Project.query.filter_by(company_id=cid).order_by(Project.created_at.desc()).all()
    users = User.query.filter_by(active=True).all()

    interactions = (
        CompanyInteraction.query
        .options(joinedload(CompanyInteraction.contact), joinedload(CompanyInteraction.user))
        .filter_by(company_id=cid)
        .order_by(CompanyInteraction.created_at.desc())
        .all()
    )
    email_templates = (
        EmailTemplate.query
        .filter_by(active=True)
        .order_by(EmailTemplate.step_order.asc(), EmailTemplate.name.asc())
        .all()
    )
    company_leads = (
        Lead.query
        .filter_by(company_id=cid)
        .order_by(Lead.created_at.desc())
        .all()
    )

    return render_template("empresa_detail.html", company=company,
                           contacts=contacts, tasks=tasks,
                           task_counts=task_counts, ideas=ideas, projects=projects, users=users,
                           interactions=interactions, email_templates=email_templates,
                           company_leads=company_leads)


@companies_bp.route("/empresas/create", methods=["POST"])
@login_required
def create():
    try:
        assigned = request.form.get("assigned_to", "").strip()
        c = Company(
            name=request.form.get("name", "").strip(),
            industry=request.form.get("industry", "").strip(),
            website=request.form.get("website", "").strip(),
            status=request.form.get("status", "por_escribir"),
            interest=request.form.get("interest", "").strip(),
            problem=request.form.get("problem", "").strip(),
            solution=request.form.get("solution", "").strip(),
            notes=request.form.get("notes", "").strip(),
            priority=request.form.get("priority", "media"),
            next_contact_date=_parse_date(request.form.get("next_contact_date")),
            source=request.form.get("source", "").strip(),
            assigned_to=int(assigned) if assigned else None,
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
        )
        db.session.add(c)
        db.session.flush()
        # Multi-assign: sync assignees table
        assigned_ids = request.form.getlist("assigned_to")
        if not assigned_ids and assigned:
            assigned_ids = [assigned]
        for uid in assigned_ids:
            uid = uid.strip()
            if uid:
                db.session.add(CompanyAssignment(company_id=c.id, user_id=int(uid)))
        _sync_assignees_to_leads(c)
        # If next_contact_date set on creation → spawn follow-up task
        _ensure_followup_task(c, prev_date=None)
        log_activity("create", "company", details=f"Nueva empresa: {c.name}")
        db.session.commit()
        push_change("companies", c.id)
        flash("Empresa creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.index"))


@companies_bp.route("/empresas/edit/<int:cid>", methods=["POST"])
@login_required
def edit(cid):
    c = db.session.get(Company, cid)
    if not c:
        flash("Empresa no encontrada", "error")
        return redirect(url_for("companies.index"))
    try:
        prev_next_date = c.next_contact_date
        assigned = request.form.get("assigned_to", "").strip()
        c.name = request.form.get("name", c.name).strip()
        c.industry = request.form.get("industry", "").strip()
        c.website = request.form.get("website", "").strip()
        c.status = request.form.get("status", c.status)
        c.interest = request.form.get("interest", "").strip()
        c.problem = request.form.get("problem", "").strip()
        c.solution = request.form.get("solution", "").strip()
        c.notes = request.form.get("notes", "").strip()
        c.priority = request.form.get("priority", c.priority or "media")
        c.next_contact_date = _parse_date(request.form.get("next_contact_date"))
        c.source = request.form.get("source", "").strip()
        c.assigned_to = int(assigned) if assigned else None
        c.phone = request.form.get("phone", "").strip()
        c.email = request.form.get("email", "").strip()
        # Multi-assign: rebuild assignees table
        assigned_ids = request.form.getlist("assigned_to")
        if not assigned_ids and assigned:
            assigned_ids = [assigned]
        CompanyAssignment.query.filter_by(company_id=c.id).delete()
        for uid in assigned_ids:
            uid = uid.strip()
            if uid:
                db.session.add(CompanyAssignment(company_id=c.id, user_id=int(uid)))
        _sync_assignees_to_leads(c)
        # Auto-create follow-up task if next_contact_date changed
        _ensure_followup_task(c, prev_date=prev_next_date)
        log_activity("update", "company", c.id, f"Editada: {c.name}")
        db.session.commit()
        push_change("companies", c.id)
        flash("Empresa actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.index"))


@companies_bp.route("/empresas/delete/<int:cid>", methods=["POST"])
@login_required
def delete(cid):
    c = db.session.get(Company, cid)
    if c:
        cid_val = c.id
        with sync_locked():
            log_activity("delete", "company", c.id, f"Eliminada: {c.name}")
            db.session.delete(c)
            db.session.commit()
            push_change_now("companies", cid_val)
        flash("Empresa eliminada", "success")
    return redirect(url_for("companies.index"))


# ═══════════════════════════════════════════
# CONTACTS CRUD
# ═══════════════════════════════════════════

@companies_bp.route("/empresas/<int:cid>/contacts/create", methods=["POST"])
@login_required
def create_contact(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)
    try:
        ct = CompanyContact(
            company_id=cid,
            name=request.form.get("name", "").strip(),
            role=request.form.get("role", "").strip(),
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(ct)
        db.session.commit()
        push_change("company_contacts", ct.id)
        flash("Contacto creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/contacts/edit/<int:ctid>", methods=["POST"])
@login_required
def edit_contact(cid, ctid):
    ct = db.session.get(CompanyContact, ctid)
    if not ct or ct.company_id != cid:
        abort(404)
    try:
        ct.name = request.form.get("name", ct.name).strip()
        ct.role = request.form.get("role", "").strip()
        ct.phone = request.form.get("phone", "").strip()
        ct.email = request.form.get("email", "").strip()
        ct.notes = request.form.get("notes", "").strip()
        db.session.commit()
        push_change("company_contacts", ct.id)
        flash("Contacto actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/contacts/delete/<int:ctid>", methods=["POST"])
@login_required
def delete_contact(cid, ctid):
    ct = db.session.get(CompanyContact, ctid)
    if ct and ct.company_id == cid:
        ctid_val = ct.id
        with sync_locked():
            db.session.delete(ct)
            db.session.commit()
            push_change_now("company_contacts", ctid_val)
        flash("Contacto eliminado", "success")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/contacts/<int:ctid>/promote", methods=["POST"])
@login_required
def promote_contact(cid, ctid):
    company = db.session.get(Company, cid)
    ct = db.session.get(CompanyContact, ctid)
    if not company or not ct or ct.company_id != cid:
        abort(404)
    try:
        from models import Client
        cname = " ".join([company.name, f"({ct.name})"])
        cli = Client(
            name=cname,
            company=company.name,
            email=ct.email or "",
            phone=ct.phone or "",
            notes=f"Contacto promovido desde Empresas: {ct.role}\n" + (ct.notes or ""),
            pipeline_stage="lead",
            source="empresa",
        )
        db.session.add(cli)
        log_activity("create", "client", details=f"Cliente promovido: {cname}")
        db.session.commit()
        push_change("clients", cli.id)
        flash("Contacto promovido a Cliente con éxito", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al promover: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


# ═══════════════════════════════════════════
# TASK CREATION FROM COMPANY
# ═══════════════════════════════════════════

@companies_bp.route("/empresas/<int:cid>/tasks/create", methods=["POST"])
@login_required
def create_task(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)
    try:
        dd = request.form.get("due_date", "").strip()
        assigned_ids = request.form.getlist("assigned_to")
        em = request.form.get("estimated_minutes", "").strip()
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            priority=request.form.get("priority", "media"),
            status="pendiente",
            due_date=datetime.strptime(dd, "%Y-%m-%d").date() if dd else None,
            company_id=cid,
            estimated_minutes=int(em) if em else 0,
        )
        db.session.add(t)
        db.session.flush()
        for uid in assigned_ids:
            uid = uid.strip()
            if uid:
                db.session.add(TaskAssignment(task_id=t.id, user_id=int(uid)))
        log_activity("create", "task", details=f"Nueva tarea: {t.title}")
        db.session.commit()
        push_change("tasks", t.id)
        for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
            push_change("task_assignments", ta.id)
        flash("Tarea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


# ═══════════════════════════════════════════
# QUICK STATUS UPDATE
# ═══════════════════════════════════════════

@companies_bp.route("/empresas/<int:cid>/status", methods=["POST"])
@login_required
def update_status(cid):
    c = db.session.get(Company, cid)
    if c:
        c.status = request.form.get("status", c.status)
        db.session.commit()
        push_change("companies", c.id)
    return redirect(url_for("companies.index"))


@companies_bp.route("/empresas/<int:cid>/quick-priority", methods=["POST"])
@login_required
def quick_priority(cid):
    c = db.session.get(Company, cid)
    if c:
        c.priority = request.form.get("priority", "media")
        db.session.commit()
        push_change("companies", c.id)
    if request.headers.get("Accept") == "application/json":
        return jsonify({"ok": True, "priority": c.priority if c else None})
    return redirect(request.referrer or url_for("companies.index"))


@companies_bp.route("/empresas/<int:cid>/quick-next-contact", methods=["POST"])
@login_required
def quick_next_contact(cid):
    c = db.session.get(Company, cid)
    if not c:
        abort(404)
    prev = c.next_contact_date
    c.next_contact_date = _parse_date(request.form.get("next_contact_date"))
    task = _ensure_followup_task(c, prev_date=prev)
    db.session.commit()
    push_change("companies", c.id)
    if task:
        push_change("tasks", task.id)
    if request.headers.get("Accept") == "application/json":
        return jsonify({
            "ok": True,
            "next_contact_date": c.next_contact_date.isoformat() if c.next_contact_date else None,
            "task_id": task.id if task else None,
        })
    return redirect(request.referrer or url_for("companies.view", cid=cid))


# ═══════════════════════════════════════════
# CSV IMPORT / EXPORT
# ═══════════════════════════════════════════

CSV_FIELDS = [
    "name", "industry", "website", "phone", "email",
    "priority", "status", "source", "next_contact_date",
    "interest", "problem", "solution", "notes",
    "contacto_nombre", "contacto_role", "contacto_phone", "contacto_email",
]


@companies_bp.route("/empresas/export.csv")
@login_required
def export_csv():
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_FIELDS)
    for c in Company.query.order_by(Company.created_at.desc()).all():
        # Pull first contact to fill the contact_* columns (round-trip with import)
        ct = CompanyContact.query.filter_by(company_id=c.id).order_by(CompanyContact.id.asc()).first()
        w.writerow([
            c.name or "", c.industry or "", c.website or "",
            c.phone or "", c.email or "",
            c.priority or "media", c.status or "por_escribir",
            c.source or "",
            c.next_contact_date.isoformat() if c.next_contact_date else "",
            c.interest or "", c.problem or "", c.solution or "", c.notes or "",
            (ct.name if ct else ""), (ct.role if ct else ""),
            (ct.phone if ct else ""), (ct.email if ct else ""),
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=empresas_{date.today().isoformat()}.csv"},
    )


@companies_bp.route("/empresas/import", methods=["POST"])
@login_required
def import_csv():
    import csv, io
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Selecciona un archivo CSV", "error")
        return redirect(url_for("companies.index"))
    try:
        raw = f.read().decode("utf-8-sig", errors="replace")
        # Auto-detect delimiter (comma vs semicolon — Excel ES uses ;)
        sample = raw[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            class _D(csv.excel):
                delimiter = ","
            dialect = _D
        reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
        # Header alias map (Spanish + English variants)
        alias = {
            "empresa": "name", "name": "name", "nombre": "name",
            "sector": "industry", "industry": "industry", "industria": "industry",
            "web": "website", "website": "website", "url": "website",
            "tel": "phone", "telefono": "phone", "teléfono": "phone", "phone": "phone",
            "email": "email", "correo": "email", "mail": "email",
            "prioridad": "priority", "priority": "priority",
            "estado": "status", "status": "status",
            "fuente": "source", "source": "source", "origen": "source",
            "proximo_contacto": "next_contact_date", "next_contact_date": "next_contact_date",
            "interes": "interest", "interés": "interest", "interest": "interest",
            "problema": "problem", "problem": "problem",
            "solucion": "solution", "solución": "solution", "solution": "solution",
            "notas": "notes", "notes": "notes", "nota": "notes",
            "contacto": "contacto_nombre", "contacto_nombre": "contacto_nombre",
            "contacto_rol": "contacto_role", "contacto_role": "contacto_role",
            "contacto_tel": "contacto_phone", "contacto_phone": "contacto_phone", "contacto_telefono": "contacto_phone",
            "contacto_email": "contacto_email",
        }
        created, updated, skipped = 0, 0, 0
        with sync_locked():
            for raw_row in reader:
                # Normalize keys
                row = {alias.get((k or "").strip().lower().lstrip("\ufeff"), (k or "").strip().lower()): (v or "").strip()
                       for k, v in raw_row.items() if k}
                name = row.get("name", "")
                if not name:
                    skipped += 1
                    continue
                existing = Company.query.filter(Company.name.ilike(name)).first()
                if existing:
                    c = existing
                    updated += 1
                else:
                    c = Company(name=name)
                    db.session.add(c)
                    created += 1
                for fld in ["industry", "website", "phone", "email",
                            "source", "interest", "problem", "solution", "notes"]:
                    val = row.get(fld, "")
                    if val:
                        setattr(c, fld, val)
                if row.get("priority") in ("alta", "media", "baja"):
                    c.priority = row["priority"]
                if row.get("status"):
                    c.status = row["status"]
                if row.get("next_contact_date"):
                    nd = _parse_date(row["next_contact_date"])
                    if nd:
                        c.next_contact_date = nd
                db.session.flush()

                # Optional contact column → upsert by email/name
                ct_name = row.get("contacto_nombre", "")
                ct_email = row.get("contacto_email", "")
                if ct_name or ct_email:
                    q = CompanyContact.query.filter_by(company_id=c.id)
                    if ct_email:
                        ct = q.filter(CompanyContact.email.ilike(ct_email)).first()
                    else:
                        ct = q.filter(CompanyContact.name.ilike(ct_name)).first()
                    if not ct:
                        ct = CompanyContact(company_id=c.id, name=ct_name or "(sin nombre)")
                        db.session.add(ct)
                    if ct_name:
                        ct.name = ct_name
                    if row.get("contacto_role"):
                        ct.role = row["contacto_role"]
                    if row.get("contacto_phone"):
                        ct.phone = row["contacto_phone"]
                    if ct_email:
                        ct.email = ct_email
                    db.session.flush()
                    push_change("company_contacts", ct.id)
                push_change("companies", c.id)
            log_activity("import", "company", details=f"CSV: +{created} nuevas, {updated} actualizadas, {skipped} omitidas")
            db.session.commit()
        flash(f"Importadas {created} nuevas, {updated} actualizadas ({skipped} omitidas).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error importando CSV: {e}", "error")
    return redirect(url_for("companies.index"))


# ═══════════════════════════════════════════
# IDEAS CRUD
# ═══════════════════════════════════════════

@companies_bp.route("/empresas/<int:cid>/ideas/create", methods=["POST"])
@login_required
def create_idea(cid):
    company = db.session.get(Company, cid)
    if not company:
        abort(404)
    try:
        idea = Idea(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            category=request.form.get("category", "feature"),
            status="nueva",
            company_id=cid,
            created_by=g.user.id if g.get("user") else None,
        )
        db.session.add(idea)
        db.session.commit()
        push_change("ideas", idea.id)
        flash("Idea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/ideas/edit/<int:iid>", methods=["POST"])
@login_required
def edit_idea(cid, iid):
    idea = db.session.get(Idea, iid)
    if not idea or idea.company_id != cid:
        abort(404)
    try:
        idea.title = request.form.get("title", idea.title).strip()
        idea.description = request.form.get("description", "").strip()
        idea.category = request.form.get("category", idea.category)
        idea.status = request.form.get("status", idea.status)
        db.session.commit()
        push_change("ideas", idea.id)
        flash("Idea actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/ideas/delete/<int:iid>", methods=["POST"])
@login_required
def delete_idea(cid, iid):
    idea = db.session.get(Idea, iid)
    if idea and idea.company_id == cid:
        idea_id = idea.id
        with sync_locked():
            db.session.delete(idea)
            db.session.commit()
            push_change_now("ideas", idea_id)
        flash("Idea eliminada", "success")
    return redirect(url_for("companies.view", cid=cid))


@companies_bp.route("/empresas/<int:cid>/ideas/vote/<int:iid>", methods=["POST"])
@login_required
def vote_idea(cid, iid):
    idea = db.session.get(Idea, iid)
    if idea and idea.company_id == cid:
        idea.votes = (idea.votes or 0) + 1
        db.session.commit()
        push_change("ideas", idea.id)
    return redirect(url_for("companies.view", cid=cid))
