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


# ─────────────────────────────────────────────────────────────────────────────
# Asistente conversacional con contexto del panel
# ─────────────────────────────────────────────────────────────────────────────

def _build_panel_context():
    """Resumen denso del estado del panel para alimentar respuestas."""
    today = date.today()
    proj_active = Project.query.filter_by(status="activo").all()
    overdue = Task.query.filter(
        Task.due_date < today,
        Task.status.in_(["pendiente", "en_progreso"]),
    ).all()
    pending = Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count()
    inv_pending = Invoice.query.filter(Invoice.status.in_(["enviada", "vencida"])).all()
    leads = Client.query.filter_by(pipeline_stage="lead").count()

    return {
        "fecha": today.isoformat(),
        "proyectos_activos": [{"id": p.id, "nombre": p.name, "progreso": p.progress or 0,
                               "deadline": p.deadline.isoformat() if p.deadline else None} for p in proj_active],
        "tareas_pendientes_total": pending,
        "tareas_atrasadas": [{"id": t.id, "titulo": t.title, "vence": t.due_date.isoformat()} for t in overdue[:10]],
        "facturas_pendientes": [{"id": i.id, "numero": i.number, "total": i.total} for i in inv_pending[:10]],
        "leads": leads,
    }


def _local_answer(question, ctx):
    """Respuesta heurística (sin red) usando palabras clave sobre el contexto."""
    q = (question or "").lower().strip()
    if not q:
        return "Hazme una pregunta sobre el panel — por ejemplo: \"¿qué tareas vencen esta semana?\""

    if any(w in q for w in ["atrasad", "vencid", "tarde"]):
        if not ctx["tareas_atrasadas"]:
            return "No tienes tareas atrasadas ahora mismo. 👌"
        lines = ["Tareas atrasadas:"]
        for t in ctx["tareas_atrasadas"]:
            lines.append(f"• {t['titulo']} (venció {t['vence']})")
        return "\n".join(lines)

    if any(w in q for w in ["proyecto", "deadline", "entrega"]):
        if not ctx["proyectos_activos"]:
            return "No hay proyectos activos."
        lines = ["Proyectos activos:"]
        for p in ctx["proyectos_activos"]:
            dl = f" · deadline {p['deadline']}" if p["deadline"] else ""
            lines.append(f"• {p['nombre']} — {p['progreso']}%{dl}")
        return "\n".join(lines)

    if any(w in q for w in ["factura", "cobr", "pendiente de cobro"]):
        if not ctx["facturas_pendientes"]:
            return "No hay facturas pendientes de cobro."
        total = sum(i["total"] or 0 for i in ctx["facturas_pendientes"])
        lines = [f"Facturas pendientes (total {total:.0f}€):"]
        for i in ctx["facturas_pendientes"]:
            lines.append(f"• {i['numero']} — {i['total']:.0f}€")
        return "\n".join(lines)

    if any(w in q for w in ["lead", "captacion", "captación", "pipeline"]):
        return f"Tienes {ctx['leads']} lead(s) en pipeline."

    if any(w in q for w in ["resumen", "como va", "cómo va", "estado"]):
        s = generate_financial_summary()
        lines = [f"Resumen financiero del mes:",
                 f"• Ingresos: {s['income']:.0f}€",
                 f"• Gastos: {s['expense']:.0f}€",
                 f"• Neto: {s['net']:.0f}€",
                 f"• Tareas pendientes: {s['pending_tasks']} ({s['overdue_tasks']} atrasadas)"]
        return "\n".join(lines)

    return ("No tengo una respuesta directa, pero el contexto actual es: "
            f"{ctx['tareas_pendientes_total']} tareas pendientes, "
            f"{len(ctx['proyectos_activos'])} proyectos activos, "
            f"{ctx['leads']} leads, "
            f"{len(ctx['facturas_pendientes'])} facturas por cobrar.")


@ai_bp.route("/api/ai/ask", methods=["POST"])
@login_required
def api_ask():
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    ctx = _build_panel_context()
    answer = _local_answer(question, ctx)
    return jsonify({"answer": answer, "context": ctx})
