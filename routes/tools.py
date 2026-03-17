from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Tool
from routes.auth import login_required
from services.activity import log_activity
from services.sync import push_change

tools_bp = Blueprint("tools", __name__)


@tools_bp.route("/herramientas")
@login_required
def index():
    cat = request.args.get("category", "")
    q = Tool.query
    if cat:
        q = q.filter_by(category=cat)
    tools = q.order_by(Tool.name).all()
    total_cost = sum(t.cost_monthly for t in Tool.query.all())
    return render_template("herramientas.html", tools=tools, total_cost=total_cost, sel_category=cat)


@tools_bp.route("/herramientas/create", methods=["POST"])
@login_required
def create():
    try:
        t = Tool(
            name=request.form.get("name", "").strip(),
            url=request.form.get("url", "").strip(),
            category=request.form.get("category", "otro"),
            cost_monthly=float(request.form.get("cost_monthly", 0) or 0),
            description=request.form.get("description", "").strip(),
            used_by=request.form.get("used_by", "ambos"),
        )
        db.session.add(t)
        log_activity("create", "tool", details=f"Nueva herramienta: {t.name}")
        db.session.commit()
        push_change("tools", t.id)
        flash("Herramienta creada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("tools.index"))


@tools_bp.route("/herramientas/edit/<int:tid>", methods=["POST"])
@login_required
def edit(tid):
    t = db.session.get(Tool, tid)
    if not t:
        flash("Herramienta no encontrada", "error")
        return redirect(url_for("tools.index"))
    try:
        t.name = request.form.get("name", t.name).strip()
        t.url = request.form.get("url", t.url).strip()
        t.category = request.form.get("category", t.category)
        t.cost_monthly = float(request.form.get("cost_monthly", t.cost_monthly) or 0)
        t.description = request.form.get("description", "").strip()
        t.used_by = request.form.get("used_by", t.used_by)
        log_activity("update", "tool", t.id, f"Editada: {t.name}")
        db.session.commit()
        push_change("tools", t.id)
        flash("Herramienta actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("tools.index"))


@tools_bp.route("/herramientas/delete/<int:tid>", methods=["POST"])
@login_required
def delete(tid):
    t = db.session.get(Tool, tid)
    if t:
        tid_val = t.id
        log_activity("delete", "tool", t.id, f"Eliminada: {t.name}")
        db.session.delete(t)
        db.session.commit()
        push_change("tools", tid_val)
        flash("Herramienta eliminada", "success")
    return redirect(url_for("tools.index"))
