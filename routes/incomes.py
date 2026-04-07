from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Income, Project
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

incomes_bp = Blueprint("incomes", __name__)


@incomes_bp.route("/ingresos")
@login_required
def index():
    cat = request.args.get("category", "")
    status = request.args.get("status", "")
    q = Income.query
    if cat:
        q = q.filter_by(category=cat)
    if status:
        q = q.filter_by(status=status)
    incomes = q.order_by(Income.created_at.desc()).all()

    cobrado = Income.query.filter_by(status="cobrado").all()
    total_cobrado = sum(i.amount for i in cobrado)

    pendiente = Income.query.filter_by(status="pendiente").all()
    total_pendiente = sum(i.amount for i in pendiente)

    facturado = Income.query.filter_by(status="facturado").all()
    total_facturado = sum(i.amount for i in facturado)

    projects = Project.query.order_by(Project.name).all()

    return render_template(
        "ingresos.html",
        incomes=incomes,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        total_facturado=total_facturado,
        projects=projects,
        sel_category=cat,
        sel_status=status,
    )


@incomes_bp.route("/ingresos/create", methods=["POST"])
@login_required
def create():
    try:
        inv = request.form.get("invoice_date", "").strip()
        paid = request.form.get("paid_date", "").strip()
        pid = request.form.get("project_id", "").strip()
        i = Income(
            name=request.form.get("name", "").strip(),
            client_name=request.form.get("client_name", "").strip(),
            amount=float(request.form.get("amount", 0) or 0),
            currency=request.form.get("currency", "EUR"),
            frequency=request.form.get("frequency", "unico"),
            category=request.form.get("category", "proyecto"),
            status=request.form.get("status", "pendiente"),
            project_id=int(pid) if pid else None,
            invoice_date=datetime.strptime(inv, "%Y-%m-%d").date() if inv else None,
            paid_date=datetime.strptime(paid, "%Y-%m-%d").date() if paid else None,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(i)
        log_activity("create", "income", details=f"Nuevo ingreso: {i.name}")
        db.session.commit()
        push_change("incomes", i.id)
        flash("Ingreso creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("incomes.index"))


@incomes_bp.route("/ingresos/edit/<int:iid>", methods=["POST"])
@login_required
def edit(iid):
    i = db.session.get(Income, iid)
    if not i:
        flash("Ingreso no encontrado", "error")
        return redirect(url_for("incomes.index"))
    try:
        i.name = request.form.get("name", i.name).strip()
        i.client_name = request.form.get("client_name", "").strip()
        i.amount = float(request.form.get("amount", i.amount) or 0)
        i.currency = request.form.get("currency", i.currency)
        i.frequency = request.form.get("frequency", i.frequency)
        i.category = request.form.get("category", i.category)
        i.status = request.form.get("status", i.status)
        pid = request.form.get("project_id", "").strip()
        i.project_id = int(pid) if pid else None
        inv = request.form.get("invoice_date", "").strip()
        i.invoice_date = datetime.strptime(inv, "%Y-%m-%d").date() if inv else None
        paid = request.form.get("paid_date", "").strip()
        i.paid_date = datetime.strptime(paid, "%Y-%m-%d").date() if paid else None
        i.notes = request.form.get("notes", "").strip()
        log_activity("update", "income", i.id, f"Editado: {i.name}")
        db.session.commit()
        push_change("incomes", i.id)
        flash("Ingreso actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("incomes.index"))


@incomes_bp.route("/ingresos/delete/<int:iid>", methods=["POST"])
@login_required
def delete(iid):
    i = db.session.get(Income, iid)
    if i:
        iid_val = i.id
        with sync_locked():
            log_activity("delete", "income", i.id, f"Eliminado: {i.name}")
            db.session.delete(i)
            db.session.commit()
            push_change_now("incomes", iid_val)
        flash("Ingreso eliminado", "success")
    return redirect(url_for("incomes.index"))
