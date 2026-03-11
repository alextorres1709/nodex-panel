from datetime import date, timedelta
from flask import Blueprint, render_template, request
from models import db, Payment, Income, Invoice, Project, Task, Client, TimeEntry
from routes.auth import login_required

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reportes")
@login_required
def index():
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))

    # ── Financial summary ──
    income_total = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
        Income.status == "cobrado",
        db.extract("month", Income.paid_date) == month,
        db.extract("year", Income.paid_date) == year,
    ).scalar()

    invoice_total = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
        Invoice.status == "cobrada",
        db.extract("month", Invoice.paid_date) == month,
        db.extract("year", Invoice.paid_date) == year,
    ).scalar()

    total_income = float(income_total) + float(invoice_total)

    active_payments = Payment.query.filter_by(status="activo").all()
    total_expense = sum(
        p.amount if p.frequency == "mensual" else p.amount / 12 if p.frequency == "anual" else 0
        for p in active_payments
    )

    # Previous month comparison
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    prev_income = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
        Income.status == "cobrado",
        db.extract("month", Income.paid_date) == prev_m,
        db.extract("year", Income.paid_date) == prev_y,
    ).scalar()
    prev_inv = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
        Invoice.status == "cobrada",
        db.extract("month", Invoice.paid_date) == prev_m,
        db.extract("year", Invoice.paid_date) == prev_y,
    ).scalar()
    prev_total_income = float(prev_income) + float(prev_inv)
    income_change = ((total_income - prev_total_income) / prev_total_income * 100) if prev_total_income else 0

    # ── Tasks stats ──
    tasks_completed = Task.query.filter(
        Task.status == "completada",
    ).count()
    tasks_pending = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count()
    tasks_overdue = Task.query.filter(
        Task.due_date < today, Task.status.in_(["pendiente", "en_progreso"])
    ).count()

    # ── Clients ──
    total_clients = Client.query.count()
    new_clients_month = Client.query.filter(
        db.extract("month", Client.created_at) == month,
        db.extract("year", Client.created_at) == year,
    ).count()
    clients_cerrado = Client.query.filter_by(pipeline_stage="cerrado").count()
    conversion_rate = (clients_cerrado / total_clients * 100) if total_clients else 0

    # ── Projects ──
    active_projects = Project.query.filter_by(status="activo").count()
    completed_projects = Project.query.filter_by(status="completado").count()

    # ── Time tracked ──
    month_hours = db.session.query(db.func.coalesce(db.func.sum(TimeEntry.minutes), 0)).filter(
        db.extract("month", TimeEntry.date) == month,
        db.extract("year", TimeEntry.date) == year,
    ).scalar()

    # ── Invoice stats ──
    invoices_pending = Invoice.query.filter(Invoice.status.in_(["enviada", "vencida"])).count()
    invoices_pending_amount = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
        Invoice.status.in_(["enviada", "vencida"])
    ).scalar()

    # Monthly chart data (6 months)
    chart_months = []
    for i in range(5, -1, -1):
        m_date = today.replace(day=1) - timedelta(days=i * 30)
        m, y = m_date.month, m_date.year
        inc = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
            Income.status == "cobrado",
            db.extract("month", Income.paid_date) == m,
            db.extract("year", Income.paid_date) == y,
        ).scalar()
        chart_months.append({"label": f"{m:02d}/{y % 100}", "income": float(inc), "expense": total_expense})

    month_names = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    return render_template(
        "reportes.html",
        month=month, year=year, month_name=month_names[month], today=today,
        total_income=total_income, total_expense=total_expense,
        net=total_income - total_expense, income_change=income_change,
        tasks_completed=tasks_completed, tasks_pending=tasks_pending, tasks_overdue=tasks_overdue,
        total_clients=total_clients, new_clients_month=new_clients_month,
        conversion_rate=conversion_rate,
        active_projects=active_projects, completed_projects=completed_projects,
        month_hours=int(month_hours), invoices_pending=invoices_pending,
        invoices_pending_amount=float(invoices_pending_amount),
        chart_months=chart_months,
    )
