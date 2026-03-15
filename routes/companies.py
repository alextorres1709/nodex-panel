from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from sqlalchemy.orm import joinedload
from models import db, Company, CompanyContact, Task, User
from routes.auth import login_required
from services.activity import log_activity

companies_bp = Blueprint("companies", __name__)


@companies_bp.route("/empresas")
@login_required
def index():
    status = request.args.get("status", "")
    q = Company.query
    if status:
        q = q.filter_by(status=status)
    companies = q.order_by(Company.created_at.desc()).all()

    # Count contacts per company
    contact_counts = {}
    for c in companies:
        contact_counts[c.id] = CompanyContact.query.filter_by(company_id=c.id).count()

    return render_template("empresas.html", companies=companies,
                           contact_counts=contact_counts, sel_status=status)


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
        "completada": sum(1 for t in tasks if t.status == "completada"),
    }
    users = User.query.filter_by(active=True).all()

    return render_template("empresa_detail.html", company=company,
                           contacts=contacts, tasks=tasks,
                           task_counts=task_counts, users=users)


@companies_bp.route("/empresas/create", methods=["POST"])
@login_required
def create():
    try:
        c = Company(
            name=request.form.get("name", "").strip(),
            industry=request.form.get("industry", "").strip(),
            website=request.form.get("website", "").strip(),
            status=request.form.get("status", "escrito"),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(c)
        log_activity("create", "company", details=f"Nueva empresa: {c.name}")
        db.session.commit()
        from services.sync import push_change
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
        c.name = request.form.get("name", c.name).strip()
        c.industry = request.form.get("industry", "").strip()
        c.website = request.form.get("website", "").strip()
        c.status = request.form.get("status", c.status)
        c.notes = request.form.get("notes", "").strip()
        log_activity("update", "company", c.id, f"Editada: {c.name}")
        db.session.commit()
        from services.sync import push_change
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
        log_activity("delete", "company", c.id, f"Eliminada: {c.name}")
        db.session.delete(c)
        db.session.commit()
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
        from services.sync import push_change
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
        from services.sync import push_change
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
        db.session.delete(ct)
        db.session.commit()
        flash("Contacto eliminado", "success")
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
        at = request.form.get("assigned_to", "").strip()
        em = request.form.get("estimated_minutes", "").strip()
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            assigned_to=int(at) if at else None,
            priority=request.form.get("priority", "media"),
            status="pendiente",
            due_date=datetime.strptime(dd, "%Y-%m-%d").date() if dd else None,
            company_id=cid,
            estimated_minutes=int(em) if em else 0,
        )
        db.session.add(t)
        db.session.flush()
        log_activity("create", "task", details=f"Nueva tarea: {t.title}")
        db.session.commit()
        from services.sync import push_change
        push_change("tasks", t.id)
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
        from services.sync import push_change
        push_change("companies", c.id)
    return redirect(url_for("companies.index"))
