from datetime import date, timedelta
from flask import Blueprint, render_template, request
from models import db, Payment, Income, Invoice
from routes.auth import login_required

balance_bp = Blueprint("balance", __name__)


@balance_bp.route("/balance")
@login_required
def index():
    today = date.today()
    year = int(request.args.get("year", today.year))

    # ── Monthly P&L for selected year ──
    months = []
    for m in range(1, 13):
        # Income: cobrado in this month
        inc = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
            Income.status == "cobrado",
            db.extract("month", Income.paid_date) == m,
            db.extract("year", Income.paid_date) == year,
        ).scalar()

        # Invoices cobradas
        inv_inc = db.session.query(db.func.coalesce(db.func.sum(Invoice.total), 0)).filter(
            Invoice.status == "cobrada",
            db.extract("month", Invoice.paid_date) == m,
            db.extract("year", Invoice.paid_date) == year,
        ).scalar()

        total_income = float(inc) + float(inv_inc)

        # Expenses: active payments prorated to monthly
        active_payments = Payment.query.filter_by(status="activo").all()
        total_expense = sum(
            p.amount if p.frequency == "mensual"
            else p.amount / 12 if p.frequency == "anual"
            else (p.amount if p.next_date and p.next_date.month == m and p.next_date.year == year else 0)
            for p in active_payments
        )

        months.append({
            "month": m,
            "label": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][m - 1],
            "income": total_income,
            "expense": total_expense,
            "net": total_income - total_expense,
        })

    # ── Annual totals ──
    annual_income = sum(m["income"] for m in months)
    annual_expense = sum(m["expense"] for m in months)
    annual_net = annual_income - annual_expense

    # ── MRR (Monthly Recurring Revenue) ──
    mrr_income = db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0)).filter(
        Income.frequency == "mensual", Income.status == "cobrado"
    ).scalar()
    mrr_expense = sum(
        p.amount for p in Payment.query.filter_by(status="activo", frequency="mensual").all()
    )

    # ── Expense breakdown by category ──
    expense_cats = (
        db.session.query(Payment.category, db.func.sum(Payment.amount))
        .filter_by(status="activo", frequency="mensual")
        .group_by(Payment.category).all()
    )

    # ── Income breakdown by category ──
    income_cats = (
        db.session.query(Income.category, db.func.sum(Income.amount))
        .filter(Income.status == "cobrado",
                db.extract("year", Income.paid_date) == year)
        .group_by(Income.category).all()
    )

    return render_template(
        "balance.html",
        year=year, today=today, months=months,
        annual_income=annual_income, annual_expense=annual_expense, annual_net=annual_net,
        mrr_income=float(mrr_income), mrr_expense=mrr_expense,
        expense_cats=expense_cats, income_cats=income_cats,
    )
