from datetime import date, timedelta
from flask import Blueprint, render_template, request, jsonify, session
from models import db, Payment, Income, Invoice, Project, Task, Client, TimeEntry
from routes.auth import login_required

ai_bp = Blueprint("ai_assistant", __name__)


def generate_financial_summary():
    """Generate AI-like financial summary from data."""
    today = date.today()
    month = today.month
    year = today.year

    # Income
    income = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
        Income.status == "cobrado",
        db.extract("month", Income.paid_date) == month,
        db.extract("year", Income.paid_date) == year,
    ).scalar()

    inv_income = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
        Invoice.status == "cobrada",
        db.extract("month", Invoice.paid_date) == month,
        db.extract("year", Invoice.paid_date) == year,
    ).scalar()

    total_income = float(income) + float(inv_income)

    # Expenses
    active_payments = Payment.query.filter_by(status="activo").all()
    total_expense = sum(
        p.amount if p.frequency == "mensual" else p.amount / 12 if p.frequency == "anual" else 0
        for p in active_payments
    )

    # Tasks
    pending = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count()
    overdue = Task.query.filter(Task.due_date < today, Task.status.in_(["pendiente", "en_progreso"])).count()

    # Clients
    total_clients = Client.query.count()
    leads = Client.query.filter_by(pipeline_stage="lead").count()

    # Invoices pending
    inv_pending = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
        Invoice.status.in_(["enviada", "vencida"])
    ).scalar()

    # Projects
    active_projects = Project.query.filter_by(status="activo").all()

    net = total_income - total_expense
    insights = []

    if net > 0:
        insights.append(f"Balance positivo este mes: +{net:.0f}€. Ingresos {total_income:.0f}€ vs gastos {total_expense:.0f}€.")
    else:
        insights.append(f"Balance negativo: {net:.0f}€. Revisa gastos o acelera cobros.")

    if overdue > 0:
        insights.append(f"Tienes {overdue} tarea(s) atrasada(s). Prioriza completarlas.")

    if float(inv_pending) > 0:
        insights.append(f"Facturas pendientes de cobro: {float(inv_pending):.0f}€. Haz seguimiento.")

    if leads > 0:
        insights.append(f"{leads} lead(s) en pipeline. Convierte con propuestas.")

    for p in active_projects:
        if p.deadline and p.deadline < today + timedelta(days=7) and p.progress < 80:
            insights.append(f"Proyecto '{p.name}' tiene deadline pronto con solo {p.progress}% progreso.")

    if pending > 5:
        insights.append(f"{pending} tareas pendientes. Considera delegar o repriorizar.")

    # Hours
    month_hours = db.session.query(db.func.coalesce(db.func.sum(TimeEntry.minutes), 0)).filter(
        db.extract("month", TimeEntry.date) == month,
        db.extract("year", TimeEntry.date) == year,
    ).scalar()
    if int(month_hours) > 0:
        insights.append(f"Has registrado {int(month_hours) // 60}h {int(month_hours) % 60}min este mes.")

    return {
        "income": total_income,
        "expense": total_expense,
        "net": net,
        "pending_tasks": pending,
        "overdue_tasks": overdue,
        "total_clients": total_clients,
        "insights": insights,
    }


@ai_bp.route("/asistente")
@login_required
def index():
    summary = generate_financial_summary()
    return render_template("asistente.html", summary=summary)


@ai_bp.route("/api/ai/summary")
@login_required
def api_summary():
    return jsonify(generate_financial_summary())
