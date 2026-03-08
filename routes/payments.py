from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Payment
from routes.auth import login_required
from services.activity import log_activity

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/pagos")
@login_required
def index():
    cat = request.args.get("category", "")
    status = request.args.get("status", "")
    q = Payment.query
    if cat:
        q = q.filter_by(category=cat)
    if status:
        q = q.filter_by(status=status)
    payments = q.order_by(Payment.created_at.desc()).all()

    active = Payment.query.filter_by(status="activo").all()
    total_monthly = sum(
        p.amount if p.frequency == "mensual" else p.amount / 12 if p.frequency == "anual" else 0
        for p in active
    )
    total_annual = total_monthly * 12

    return render_template(
        "pagos.html",
        payments=payments,
        total_monthly=total_monthly,
        total_annual=total_annual,
        sel_category=cat,
        sel_status=status,
    )


@payments_bp.route("/pagos/create", methods=["POST"])
@login_required
def create():
    try:
        nd = request.form.get("next_date", "").strip()
        p = Payment(
            name=request.form.get("name", "").strip(),
            amount=float(request.form.get("amount", 0) or 0),
            currency=request.form.get("currency", "EUR"),
            frequency=request.form.get("frequency", "mensual"),
            category=request.form.get("category", "otro"),
            status=request.form.get("status", "activo"),
            next_date=datetime.strptime(nd, "%Y-%m-%d").date() if nd else None,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(p)
        log_activity("create", "payment", details=f"Nuevo pago: {p.name}")
        db.session.commit()
        flash("Pago creado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("payments.index"))


@payments_bp.route("/pagos/edit/<int:pid>", methods=["POST"])
@login_required
def edit(pid):
    p = db.session.get(Payment, pid)
    if not p:
        flash("Pago no encontrado", "error")
        return redirect(url_for("payments.index"))
    try:
        p.name = request.form.get("name", p.name).strip()
        p.amount = float(request.form.get("amount", p.amount) or 0)
        p.currency = request.form.get("currency", p.currency)
        p.frequency = request.form.get("frequency", p.frequency)
        p.category = request.form.get("category", p.category)
        p.status = request.form.get("status", p.status)
        nd = request.form.get("next_date", "").strip()
        p.next_date = datetime.strptime(nd, "%Y-%m-%d").date() if nd else None
        p.notes = request.form.get("notes", "").strip()
        log_activity("update", "payment", p.id, f"Editado: {p.name}")
        db.session.commit()
        flash("Pago actualizado", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("payments.index"))


@payments_bp.route("/pagos/delete/<int:pid>", methods=["POST"])
@login_required
def delete(pid):
    p = db.session.get(Payment, pid)
    if p:
        log_activity("delete", "payment", p.id, f"Eliminado: {p.name}")
        db.session.delete(p)
        db.session.commit()
        flash("Pago eliminado", "success")
    return redirect(url_for("payments.index"))
