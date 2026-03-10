from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, Client, Project, Income, Invoice
from routes.auth import login_required
from services.activity import log_activity

clients_bp = Blueprint("clients", __name__)


@clients_bp.route("/clientes")
@login_required
def index():
    stage = request.args.get("stage", "")
    q = Client.query
    if stage:
        q = q.filter_by(pipeline_stage=stage)
    clients = q.order_by(Client.created_at.desc()).all()

    stages = {
        "lead": Client.query.filter_by(pipeline_stage="lead").count(),
        "propuesta": Client.query.filter_by(pipeline_stage="propuesta").count(),
        "negociacion": Client.query.filter_by(pipeline_stage="negociacion").count(),
        "cerrado": Client.query.filter_by(pipeline_stage="cerrado").count(),
        "perdido": Client.query.filter_by(pipeline_stage="perdido").count(),
    }

    return render_template("clientes.html", clients=clients, stages=stages, current_stage=stage)


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
    log_activity(g.user.id, "create", "client", c.id, c.name)
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
    log_activity(g.user.id, "update", "client", c.id, c.name)
    flash("Cliente actualizado", "success")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = Client.query.get_or_404(cid)
    name = c.name
    db.session.delete(c)
    db.session.commit()
    log_activity(g.user.id, "delete", "client", cid, name)
    flash("Cliente eliminado", "success")
    return redirect(url_for("clients.index"))


@clients_bp.route("/clientes/<int:cid>/stage", methods=["POST"])
@login_required
def update_stage(cid):
    c = Client.query.get_or_404(cid)
    new_stage = request.form.get("stage", c.pipeline_stage)
    c.pipeline_stage = new_stage
    db.session.commit()
    log_activity(g.user.id, "update", "client", c.id, f"{c.name} → {new_stage}")
    return redirect(url_for("clients.index"))
