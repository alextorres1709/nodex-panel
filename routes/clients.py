from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, Client, Project, Income, Invoice
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

clients_bp = Blueprint("clients", __name__)


@clients_bp.route("/clientes")
@login_required
def index():
    stage = request.args.get("stage", "")
    q = Client.query
    if stage:
        q = q.filter_by(pipeline_stage=stage)
    
    # 1. Fetch official clients
    real_clients = q.order_by(Client.created_at.desc()).all()
    all_real_clients = Client.query.order_by(Client.created_at.desc()).all()

    # 2. Fetch Company contacts and mock them to look like clients
    from models import CompanyContact
    all_contacts = CompanyContact.query.all()
    
    mock_contacts = []
    for ct in all_contacts:
        company_name = ct.company.name if ct.company else ""
        mock_contacts.append({
            "id": f"contact_{ct.id}",
            "real_id": ct.id,
            "is_contact": True,
            "name": f"{ct.name} ({ct.role or 'Contacto'})",
            "raw_name": ct.name,
            "role": ct.role or "",
            "company": company_name,
            "company_id": ct.company_id,
            "email": ct.email or "",
            "phone": ct.phone or "",
            "pipeline_stage": "lead", # Treat contacts as leads by default
            "source": "Empresas",
            "notes": ct.notes or ""
        })

    # 3. Filter contacts based on current stage
    filtered_contacts = []
    if not stage or stage == "lead":
        filtered_contacts = mock_contacts

    # 4. Merge
    clients = list(real_clients) + filtered_contacts
    all_clients = list(all_real_clients) + mock_contacts

    stages = {
        "lead": Client.query.filter_by(pipeline_stage="lead").count() + len(mock_contacts),
        "propuesta": Client.query.filter_by(pipeline_stage="propuesta").count(),
        "negociacion": Client.query.filter_by(pipeline_stage="negociacion").count(),
        "cerrado": Client.query.filter_by(pipeline_stage="cerrado").count(),
        "perdido": Client.query.filter_by(pipeline_stage="perdido").count(),
    }

    return render_template("clientes.html", clients=clients, all_clients=all_clients, stages=stages, current_stage=stage)


@clients_bp.route("/clientes/new", methods=["POST"])
@login_required
def create():
    c = Client(
        name=request.form.get("name", ""),
        company=request.form.get("company", ""),
        email=request.form.get("email", ""),
        phone=request.form.get("phone", ""),
        address=request.form.get("address", ""),
        nif=request.form.get("nif", ""),
        tags=request.form.get("tags", ""),
        pipeline_stage=request.form.get("pipeline_stage", "lead"),
        source=request.form.get("source", ""),
        notes=request.form.get("notes", ""),
    )
    db.session.add(c)
    db.session.commit()
    push_change("clients", c.id)
    log_activity("create", "client", c.id, f"Nuevo cliente: {c.name}")
    flash("Cliente creado", "success")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/<int:cid>/edit", methods=["POST"])
@login_required
def edit(cid):
    c = Client.query.get_or_404(cid)
    c.name = request.form.get("name", c.name)
    c.company = request.form.get("company", c.company)
    c.email = request.form.get("email", c.email)
    c.phone = request.form.get("phone", c.phone)
    c.address = request.form.get("address", c.address)
    c.nif = request.form.get("nif", c.nif)
    c.tags = request.form.get("tags", c.tags)
    c.pipeline_stage = request.form.get("pipeline_stage", c.pipeline_stage)
    c.source = request.form.get("source", c.source)
    c.notes = request.form.get("notes", c.notes)
    db.session.commit()
    push_change("clients", c.id)
    log_activity("update", "client", c.id, f"Cliente actualizado: {c.name}")
    flash("Cliente actualizado", "success")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = Client.query.get_or_404(cid)
    name = c.name
    with sync_locked():
        log_activity("delete", "client", cid, f"Cliente eliminado: {name}")
        db.session.delete(c)
        db.session.commit()
        push_change_now("clients", cid)
    flash("Cliente eliminado", "success")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/<int:cid>/stage", methods=["POST"])
@login_required
def update_stage(cid):
    c = Client.query.get_or_404(cid)
    new_stage = request.form.get("stage", c.pipeline_stage)
    c.pipeline_stage = new_stage
    db.session.commit()
    push_change("clients", c.id)
    log_activity("update", "client", c.id, f"{c.name} → {new_stage}")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/contact/<int:ctid>/edit", methods=["POST"])
@login_required
def edit_contact(ctid):
    from models import CompanyContact
    ct = CompanyContact.query.get_or_404(ctid)
    ct.name = request.form.get("name", ct.name)
    ct.role = request.form.get("role", ct.role)
    ct.email = request.form.get("email", ct.email)
    ct.phone = request.form.get("phone", ct.phone)
    ct.notes = request.form.get("notes", ct.notes)
    
    db.session.commit()
    push_change("companies", ct.company_id)
    log_activity("update", "company_contact", ct.id, f"Contacto actualizado: {ct.name}")
    flash("Contacto de empresa actualizado", "success")
    return redirect(url_for("clients.index"))
