from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, Income, Project
from routes.auth import login_required
from services.activity import log_activity

incomes_bp = Blueprint("incomes", __name__)


def _run_in_app(app, fn):
    with app.app_context():
        return fn()


@incomes_bp.route("/ingresos")
@login_required
def index():
    app = current_app._get_current_object()
    cat = request.args.get("category", "")
    status = request.args.get("status", "")

    def q_incomes():
        q = Income.query
        if cat:
            q = q.filter_by(category=cat)
        if status:
            q = q.filter_by(status=status)
        return q.order_by(Income.created_at.desc()).all()

    def q_cobrado():
        rows = Income.query.filter_by(status="cobrado").all()
        return sum(i.amount for i in rows)

    def q_pendiente():
        rows = Income.query.filter_by(status="pendiente").all()
        return sum(i.amount for i in rows)

    def q_facturado():
        rows = Income.query.filter_by(status="facturado").all()
        return sum(i.amount for i in rows)

    def q_projects():
        return Project.query.order_by(Project.name).all()

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_incomes = pool.submit(_run_in_app, app, q_incomes)
        f_cobrado = pool.submit(_run_in_app, app, q_cobrado)
        f_pendiente = pool.submit(_run_in_app, app, q_pendiente)
        f_facturado = pool.submit(_run_in_app, app, q_facturado)
        f_projects = pool.submit(_run_in_app, app, q_projects)

    incomes = f_incomes.result()
    total_cobrado = f_cobrado.result()
    total_pendiente = f_pendiente.result()
    total_facturado = f_facturado.result()
    projects = f_projects.result()

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
        log_activity("delete", "income", i.id, f"Eliminado: {i.name}")
        db.session.delete(i)
        db.session.commit()
        flash("Ingreso eliminado", "success")
    return redirect(url_for("incomes.index"))
