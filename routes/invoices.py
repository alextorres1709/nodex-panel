import json
from datetime import datetime, date
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, session, g
from models import db, Invoice, Client, Project, CompanyInfo
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change, push_change_now, sync_locked

invoices_bp = Blueprint("invoices", __name__)


def _gcal_push_item(item):
    try:
        from services import gcal as gcal_svc
        if gcal_svc.is_configured() and gcal_svc.is_connected(g.user.id):
            gcal_svc.push_item("invoice", item, g.user.id)
    except Exception:
        pass


def _gcal_delete_item(item_id):
    try:
        from services import gcal as gcal_svc
        if gcal_svc.is_configured() and gcal_svc.is_connected(g.user.id):
            gcal_svc.delete_item_event("invoice", item_id, g.user.id)
    except Exception:
        pass


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
        _gcal_push_item(inv)
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
        _gcal_push_item(inv)
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
        # Remove from GCal when paid/draft; keep when outstanding
        if status in ("cobrada", "borrador"):
            _gcal_delete_item(inv.id)
        else:
            _gcal_push_item(inv)
        push_change("invoices", inv.id)
        flash(f"Factura marcada como {status}", "success")
    return redirect(url_for("invoices.index"))


@invoices_bp.route("/facturas/<int:iid>/delete", methods=["POST"])
@login_required
def delete(iid):
    inv = db.session.get(Invoice, iid)
    if inv:
        inv_id = inv.id
        _gcal_delete_item(inv_id)
        with sync_locked():
            log_activity("delete", "invoice", inv.id, f"Eliminada: {inv.number}")
            db.session.delete(inv)
            db.session.commit()
            push_change_now("invoices", inv_id)
        flash("Factura eliminada", "success")
    return redirect(url_for("invoices.index"))


def _build_invoice_pdf(inv, items, company):
    """Construye una factura PDF con reportlab y devuelve los bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    body = styles["Normal"]

    story = []

    # Cabecera
    company_name = (company.name if company else "NodexAI")
    company_email = (company.email if company else "")
    company_web = (company.website if company else "")
    story.append(Paragraph(company_name, h1))
    if company_email or company_web:
        story.append(Paragraph(f"{company_email} · {company_web}", small))
    story.append(Spacer(1, 8))

    # Bloque factura/cliente
    invoice_meta = [
        ["Factura", inv.number or "—"],
        ["Fecha", inv.invoice_date.isoformat() if inv.invoice_date else "—"],
        ["Estado", (inv.status or "").capitalize()],
    ]
    client_meta = [
        ["Cliente", inv.client_name or "—"],
        ["Email", getattr(inv, "client_email", "") or ""],
    ]
    head_table = Table([
        [Table(invoice_meta, colWidths=[28 * mm, 50 * mm]),
         Table(client_meta, colWidths=[22 * mm, 60 * mm])]
    ], colWidths=[80 * mm, 90 * mm])
    head_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(head_table)
    story.append(Spacer(1, 14))

    # Tabla de líneas
    rows = [["Concepto", "Cant.", "Precio", "Total"]]
    for it in items:
        qty = float(it.get("quantity", 1) or 1)
        price = float(it.get("price", 0) or 0)
        total_line = qty * price
        rows.append([
            it.get("description", ""),
            f"{qty:g}",
            f"{price:.2f} €",
            f"{total_line:.2f} €",
        ])
    items_table = Table(rows, colWidths=[95 * mm, 20 * mm, 25 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # Totales
    subtotal = sum(float(it.get("quantity", 1) or 1) * float(it.get("price", 0) or 0) for it in items)
    tax_rate = float(getattr(inv, "tax_rate", 0) or 0)
    tax = subtotal * tax_rate / 100.0
    total = subtotal + tax
    totals = [
        ["Subtotal", f"{subtotal:.2f} €"],
        [f"IVA ({tax_rate:g}%)", f"{tax:.2f} €"],
        ["TOTAL", f"{total:.2f} €"],
    ]
    totals_table = Table(totals, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]))
    story.append(totals_table)

    if inv.notes:
        story.append(Spacer(1, 18))
        story.append(Paragraph("<b>Notas</b>", body))
        story.append(Paragraph(inv.notes.replace("\n", "<br/>"), small))

    doc.build(story)
    return buf.getvalue()


@invoices_bp.route("/facturas/<int:iid>/pdf")
@login_required
def download_pdf(iid):
    """Genera y descarga la factura como PDF (reportlab).
    Si reportlab no está instalado, cae al template HTML como fallback."""
    inv = db.session.get(Invoice, iid)
    if not inv:
        flash("Factura no encontrada", "error")
        return redirect(url_for("invoices.index"))

    items = json.loads(inv.items) if inv.items else []
    company = CompanyInfo.query.first()

    try:
        pdf_bytes = _build_invoice_pdf(inv, items, company)
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'inline; filename="factura_{inv.number}.pdf"'
        return response
    except ImportError:
        # Fallback: HTML si reportlab no está disponible
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
