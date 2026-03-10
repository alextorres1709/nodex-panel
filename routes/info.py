from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, CompanyInfo
from routes.auth import login_required, admin_required
from services.activity import log_activity

info_bp = Blueprint("info", __name__)


@info_bp.route("/info")
@login_required
def index():
    company = CompanyInfo.query.first()
    return render_template("info.html", company=company)


@info_bp.route("/changelog")
@login_required
def changelog():
    return render_template("changelog.html")


@info_bp.route("/info/edit", methods=["POST"])
@admin_required
def edit():
    company = CompanyInfo.query.first()
    if not company:
        company = CompanyInfo()
        db.session.add(company)
    try:
        company.name = request.form.get("name", company.name).strip()
        company.description = request.form.get("description", "").strip()
        company.phone = request.form.get("phone", "").strip()
        company.email = request.form.get("email", "").strip()
        company.address = request.form.get("address", "").strip()
        company.website = request.form.get("website", "").strip()
        company.nif = request.form.get("nif", "").strip()
        company.founded = request.form.get("founded", "").strip()
        company.sector = request.form.get("sector", "").strip()
        company.linkedin = request.form.get("linkedin", "").strip()
        company.github = request.form.get("github", "").strip()
        company.extra_info = request.form.get("extra_info", "").strip()
        log_activity("update", "company_info", details="Info de empresa actualizada")
        db.session.commit()
        flash("Informacion actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(url_for("info.index"))
