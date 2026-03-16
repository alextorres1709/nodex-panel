from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from sqlalchemy.orm import joinedload
from models import db, Project, ProjectContact, Task, TaskAssignment, Subtask, TimeEntry, Document, Invoice, Income, Idea, User, Client
from routes.auth import login_required
from services.activity import log_activity

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/proyectos")
@login_required
def index():
    status = request.args.get("status", "")
    ptype = request.args.get("type", "")
    q = Project.query
    if status:
        q = q.filter_by(status=status)
    if ptype:
        q = q.filter_by(type=ptype)
    projects = q.order_by(Project.created_at.desc()).all()
    return render_template("proyectos.html", projects=projects, sel_status=status, sel_type=ptype)


@projects_bp.route("/proyectos/<int:pid>")
@login_required
def view(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)

    tasks = Task.query.filter_by(project_id=pid).order_by(Task.created_at.desc()).all()
    task_counts = {
        "pendiente": sum(1 for t in tasks if t.status == "pendiente"),
        "en_progreso": sum(1 for t in tasks if t.status == "en_progreso"),
        "completada": sum(1 for t in tasks if t.status == "completada"),
    }

    time_entries = TimeEntry.query.options(
        joinedload(TimeEntry.user)
    ).filter_by(project_id=pid).order_by(TimeEntry.date.desc()).limit(20).all()
    total_minutes = sum(e.minutes for e in TimeEntry.query.filter_by(project_id=pid).all())

    documents = Document.query.filter_by(project_id=pid).order_by(Document.created_at.desc()).all()

    invoices = Invoice.query.filter_by(project_id=pid).order_by(Invoice.created_at.desc()).all()
    total_invoiced = sum(i.total for i in invoices)

    incomes = Income.query.filter_by(project_id=pid).order_by(Income.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)

    contacts = ProjectContact.query.filter_by(project_id=pid).order_by(ProjectContact.created_at.desc()).all()
    ideas = Idea.query.filter_by(project_id=pid).order_by(Idea.created_at.desc()).all()
    proposals = [d for d in documents if d.category == "propuesta"]
    users = User.query.filter_by(active=True).all()

    return render_template(
        "proyecto_detail.html", project=project, tasks=tasks, task_counts=task_counts,
        time_entries=time_entries, total_minutes=total_minutes,
        documents=documents, invoices=invoices, total_invoiced=total_invoiced,
        incomes=incomes, total_income=total_income,
        contacts=contacts, ideas=ideas, proposals=proposals, users=users,
    )


@projects_bp.route("/proyectos/create", methods=["POST"])
@login_required
def create():
    try:
        dl = request.form.get("deadline", "").strip()
        p = Project(
            name=request.form.get("name", "").strip(),
            client_name=request.form.get("client_name", "").strip(),
            status=request.form.get("status", "activo"),
            type=request.form.get("type", "web"),
            budget=float(request.form.get("budget", 0) or 0),
            progress=int(request.form.get("progress", 0) or 0),
            deadline=datetime.strptime(dl, "%Y-%m-%d").date() if dl else None,
            description=request.form.get("description", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(p)
        log_activity("create", "project", details=f"Nuevo proyecto: {p.name}")
        db.session.commit()
        flash("Proyecto creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.index"))


@projects_bp.route("/proyectos/edit/<int:pid>", methods=["POST"])
@login_required
def edit(pid):
    p = db.session.get(Project, pid)
    if not p:
        flash("Proyecto no encontrado", "error")
        return redirect(url_for("projects.index"))
    try:
        p.name = request.form.get("name", p.name).strip()
        p.client_name = request.form.get("client_name", p.client_name).strip()
        p.status = request.form.get("status", p.status)
        p.type = request.form.get("type", p.type)
        p.budget = float(request.form.get("budget", p.budget) or 0)
        p.progress = int(request.form.get("progress", p.progress) or 0)
        dl = request.form.get("deadline", "").strip()
        p.deadline = datetime.strptime(dl, "%Y-%m-%d").date() if dl else None
        p.description = request.form.get("description", "").strip()
        p.notes = request.form.get("notes", "").strip()
        log_activity("update", "project", p.id, f"Editado: {p.name}")
        db.session.commit()
        flash("Proyecto actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.index"))


@projects_bp.route("/proyectos/delete/<int:pid>", methods=["POST"])
@login_required
def delete(pid):
    p = db.session.get(Project, pid)
    if p:
        log_activity("delete", "project", p.id, f"Eliminado: {p.name}")
        db.session.delete(p)
        db.session.commit()
        flash("Proyecto eliminado", "success")
    return redirect(url_for("projects.index"))


def _sync_contact_to_client(name, email, phone, role, project_name):
    """Create or update a Client record when a project contact is saved."""
    client = None
    if email:
        client = Client.query.filter_by(email=email).first()
    if not client:
        client = Client.query.filter_by(name=name).first()
    if client:
        if phone and not client.phone:
            client.phone = phone
        if email and not client.email:
            client.email = email
    else:
        client = Client(
            name=name,
            email=email or "",
            phone=phone or "",
            notes=f"Contacto de proyecto: {project_name}" if project_name else "",
            pipeline_stage="lead",
            source="proyecto",
        )
        db.session.add(client)


# ═══════════════════════════════════════════
# CONTACTS CRUD
# ═══════════════════════════════════════════

@projects_bp.route("/proyectos/<int:pid>/contacts/create", methods=["POST"])
@login_required
def create_contact(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)
    try:
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()
        c = ProjectContact(
            project_id=pid, name=name, role=role,
            phone=phone, email=email, notes=notes,
        )
        db.session.add(c)
        # Also create/update in Clients
        _sync_contact_to_client(name, email, phone, role, project.name)
        db.session.commit()
        from services.sync import push_change
        push_change("project_contacts", c.id)
        flash("Contacto creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.view", pid=pid))


@projects_bp.route("/proyectos/<int:pid>/contacts/edit/<int:cid>", methods=["POST"])
@login_required
def edit_contact(pid, cid):
    c = db.session.get(ProjectContact, cid)
    if not c or c.project_id != pid:
        abort(404)
    project = db.session.get(Project, pid)
    try:
        c.name = request.form.get("name", c.name).strip()
        c.role = request.form.get("role", "").strip()
        c.phone = request.form.get("phone", "").strip()
        c.email = request.form.get("email", "").strip()
        c.notes = request.form.get("notes", "").strip()
        # Also update in Clients
        _sync_contact_to_client(c.name, c.email, c.phone, c.role, project.name if project else "")
        db.session.commit()
        from services.sync import push_change
        push_change("project_contacts", c.id)
        flash("Contacto actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.view", pid=pid))


@projects_bp.route("/proyectos/<int:pid>/contacts/delete/<int:cid>", methods=["POST"])
@login_required
def delete_contact(pid, cid):
    c = db.session.get(ProjectContact, cid)
    if c and c.project_id == pid:
        db.session.delete(c)
        db.session.commit()
        flash("Contacto eliminado", "success")
    return redirect(url_for("projects.view", pid=pid))


# ═══════════════════════════════════════════
# TASK CREATION FROM PROJECT
# ═══════════════════════════════════════════

@projects_bp.route("/proyectos/<int:pid>/tasks/create", methods=["POST"])
@login_required
def create_task(pid):
    project = db.session.get(Project, pid)
    if not project:
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
            project_id=pid,
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
        from services.sync import push_change
        push_change("tasks", t.id)
        for ta in TaskAssignment.query.filter_by(task_id=t.id).all():
            push_change("task_assignments", ta.id)
        flash("Tarea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.view", pid=pid))


# ═══════════════════════════════════════════
# IDEAS CRUD
# ═══════════════════════════════════════════

@projects_bp.route("/proyectos/<int:pid>/ideas/create", methods=["POST"])
@login_required
def create_idea(pid):
    project = db.session.get(Project, pid)
    if not project:
        abort(404)
    try:
        idea = Idea(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            category=request.form.get("category", "feature"),
            status="nueva",
            project_id=pid,
            created_by=g.user.id if hasattr(g, "user") and g.user else None,
        )
        db.session.add(idea)
        db.session.commit()
        from services.sync import push_change
        push_change("ideas", idea.id)
        flash("Idea creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.view", pid=pid))


@projects_bp.route("/proyectos/<int:pid>/ideas/edit/<int:iid>", methods=["POST"])
@login_required
def edit_idea(pid, iid):
    idea = db.session.get(Idea, iid)
    if not idea or idea.project_id != pid:
        abort(404)
    try:
        idea.title = request.form.get("title", idea.title).strip()
        idea.description = request.form.get("description", "").strip()
        idea.category = request.form.get("category", idea.category)
        idea.status = request.form.get("status", idea.status)
        db.session.commit()
        from services.sync import push_change
        push_change("ideas", idea.id)
        flash("Idea actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("projects.view", pid=pid))


@projects_bp.route("/proyectos/<int:pid>/ideas/delete/<int:iid>", methods=["POST"])
@login_required
def delete_idea(pid, iid):
    idea = db.session.get(Idea, iid)
    if idea and idea.project_id == pid:
        db.session.delete(idea)
        db.session.commit()
        flash("Idea eliminada", "success")
    return redirect(url_for("projects.view", pid=pid))


@projects_bp.route("/proyectos/<int:pid>/ideas/vote/<int:iid>", methods=["POST"])
@login_required
def vote_idea(pid, iid):
    idea = db.session.get(Idea, iid)
    if idea and idea.project_id == pid:
        idea.votes = (idea.votes or 0) + 1
        db.session.commit()
    return redirect(url_for("projects.view", pid=pid))
