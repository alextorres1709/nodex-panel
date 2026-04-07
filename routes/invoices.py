import json
from datetime import datetime, date
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, session
from models import db, Invoice, Client, Project, CompanyInfo
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

invoices_bp = Blueprint("invoices", __name__)


def next_invoice_number():
    last = Invoice.query.order_by(Invoice.id.desc()).first()
    if last:
        try:
            num = int(last.number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f"FAC-{date.today().year}-{num:04d}"


@invoices_bp.route("/facturas")
@login_required
def index():
    status = request.args.get("status", "")
    q = Invoice.query
    if status:
        q = q.filter_by(status=status)
    invoices = q.order_by(Invoice.created_at.desc()).all()
    clients = Client.query.order_by(Client.name).all()
    projects = Project.query.order_by(Project.name).all()

    totals = {
        "borrador": sum(i.total for i in invoices if i.status == "borrador"),
        "enviada": sum(i.total for i in invoices if i.status == "enviada"),
        "cobrada": sum(i.total for i in invoices if i.status == "cobrada"),
        "vencida": sum(i.total for i in invoices if i.status == "vencida"),
    }

    return render_template("facturas.html", invoices=invoices, clients=clients,
                           projects=projects, sel_status=status, totals=totals,
                           next_number=next_invoice_number())


@invoices_bp.route("/facturas/create", methods=["POST"])
@login_required
def create():
    try:
        items_json = request.form.get("items_json", "[]")
        items = json.loads(items_json)
        subtotal = sum(float(it.get("qty", 0)) * float(it.get("unit_price", 0)) for it in items)
        tax_rate = float(request.form.get("tax_rate", 21))
        tax_amount = subtotal * tax_rate / 100
        total = subtotal + tax_amount

        cid = request.form.get("client_id", "").strip()
        pid = request.form.get("project_id", "").strip()
        issue = request.form.get("issue_date", "").strip()
        due = request.form.get("due_date", "").strip()

        inv = Invoice(
            number=request.form.get("number", next_invoice_number()).strip(),
            client_id=int(cid) if cid else None,
            project_id=int(pid) if pid else None,
            items=json.dumps(items),
            subtotal=subtotal,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total=total,
            status=request.form.get("status", "borrador"),
            issue_date=datetime.strptime(issue, "%Y-%m-%d").date() if issue else date.today(),
            due_date=datetime.strptime(due, "%Y-%m-%d").date() if due else None,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(inv)
        log_activity("create", "invoice", details=f"Factura {inv.number}")
        db.session.commit()
        push_change("invoices", inv.id)
        flash("Factura creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("invoices.index"))


@invoices_bp.route("/facturas/<int:iid>/edit", methods=["POST"])
@login_required
def edit(iid):
    inv = db.session.get(Invoice, iid)
    if not inv:
        flash("Factura no encontrada", "error")
        return redirect(url_for("invoices.index"))
    try:
        items_json = request.form.get("items_json", "[]")
        items = json.loads(items_json)
        inv.items = json.dumps(items)
        inv.subtotal = sum(float(it.get("qty", 0)) * float(it.get("unit_price", 0)) for it in items)
        inv.tax_rate = float(request.form.get("tax_rate", inv.tax_rate))
        inv.tax_amount = inv.subtotal * inv.tax_rate / 100
        inv.total = inv.subtotal + inv.tax_amount

        cid = request.form.get("client_id", "").strip()
        pid = request.form.get("project_id", "").strip()
        inv.client_id = int(cid) if cid else None
        inv.project_id = int(pid) if pid else None
        inv.status = request.form.get("status", inv.status)
        issue = request.form.get("issue_date", "").strip()
        due = request.form.get("due_date", "").strip()
        inv.issue_date = datetime.strptime(issue, "%Y-%m-%d").date() if issue else inv.issue_date
        inv.due_date = datetime.strptime(due, "%Y-%m-%d").date() if due else None
        inv.notes = request.form.get("notes", "").strip()

        if inv.status == "cobrada" and not inv.paid_date:
            inv.paid_date = date.today()

        log_activity("update", "invoice", inv.id, f"Factura {inv.number}")
        db.session.commit()
        push_change("invoices", inv.id)
        flash("Factura actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("invoices.index"))


@invoices_bp.route("/facturas/<int:iid>/status/<status>", methods=["POST"])
@login_required
def change_status(iid, status):
    inv = db.session.get(Invoice, iid)
    if inv and status in ("borrador", "enviada", "cobrada", "vencida"):
        inv.status = status
        if status == "cobrada":
            inv.paid_date = date.today()
        log_activity("update", "invoice", inv.id, f"Estado → {status}: {inv.number}")
        db.session.commit()
        push_change("invoices", inv.id)
        flash(f"Factura marcada como {status}", "success")
    return redirect(url_for("invoices.index"))


@invoices_bp.route("/facturas/<int:iid>/delete", methods=["POST"])
@login_required
def delete(iid):
    inv = db.session.get(Invoice, iid)
    if inv:
        inv_id = inv.id
        with sync_locked():
            log_activity("delete", "invoice", inv.id, f"Eliminada: {inv.number}")
            db.session.delete(inv)
            db.session.commit()
            push_change_now("invoices", inv_id)
        flash("Factura eliminada", "success")
    return redirect(url_for("invoices.index"))


@invoices_bp.route("/facturas/<int:iid>/pdf")
@login_required
def download_pdf(iid):
    """Generate PDF invoice using HTML rendering."""
    inv = db.session.get(Invoice, iid)
    if not inv:
        flash("Factura no encontrada", "error")
        return redirect(url_for("invoices.index"))

    items = json.loads(inv.items) if inv.items else []
    company = CompanyInfo.query.first()

    html = render_template("factura_pdf.html", invoice=inv, items=items, company=company)

    response = make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Content-Disposition"] = f"inline; filename=factura_{inv.number}.html"
    return response


@invoices_bp.route("/facturas/<int:iid>/view")
@login_required
def view(iid):
    inv = db.session.get(Invoice, iid)
    if not inv:
        flash("Factura no encontrada", "error")
        return redirect(url_for("invoices.index"))
    items = json.loads(inv.items) if inv.items else []
    company = CompanyInfo.query.first()
    return render_template("factura_view.html", invoice=inv, items=items, company=company)
