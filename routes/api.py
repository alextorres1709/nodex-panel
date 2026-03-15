"""
REST API v2 — Full JSON API for APK/mobile app and external integrations.
All endpoints require Bearer token or active session.
"""
import json
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, jsonify, request, g
from sqlalchemy.orm import joinedload
from models import (
    db, User, Project, Task, Subtask, Client, Invoice, Payment,
    Income, TimeEntry, Notification, Idea, Automation, Document,
)
from config import APP_VERSION
from routes.auth import api_token_required

api_bp = Blueprint("api", __name__)

DOWNLOAD_URL = "https://github.com/alextorres1709/nodex-panel/releases/latest/download/NodexAI-Panel.dmg"


# ═══════════════════════════════════════
# PUBLIC
# ═══════════════════════════════════════

@api_bp.route("/api/search")
def api_search():
    """Global search across tasks, projects, clients, and pages."""
    q = (request.args.get("q") or "").strip().lower()
    if not q or len(q) < 2:
        return jsonify({"results": []})
    results = []
    pages = [
        {"title": "Dashboard", "url": "/dashboard", "icon": "grid"},
        {"title": "Tareas", "url": "/tasks", "icon": "check"},
        {"title": "Proyectos", "url": "/projects", "icon": "folder"},
        {"title": "Clientes", "url": "/clients", "icon": "users"},
        {"title": "Pagos", "url": "/payments", "icon": "card"},
        {"title": "Ingresos", "url": "/incomes", "icon": "dollar"},
        {"title": "Facturas", "url": "/invoices", "icon": "file"},
        {"title": "Time Tracking", "url": "/timetracking", "icon": "clock"},
        {"title": "Calendario", "url": "/calendar", "icon": "calendar"},
{"title": "Ideas", "url": "/ideas", "icon": "idea"},
        {"title": "Herramientas", "url": "/tools", "icon": "tool"},
        {"title": "Reportes", "url": "/reports", "icon": "report"},
        {"title": "Documentos", "url": "/documents", "icon": "file"},
        {"title": "Credenciales", "url": "/credentials", "icon": "lock"},
        {"title": "Balance P&L", "url": "/balance", "icon": "chart"},
        {"title": "Changelog", "url": "/changelog", "icon": "file"},
    ]
    for p in pages:
        if q in p["title"].lower():
            results.append({"type": "page", "title": p["title"], "url": p["url"], "icon": p["icon"]})
    try:
        for t in Task.query.filter(Task.title.ilike(f"%{q}%")).limit(5).all():
            results.append({"type": "task", "title": t.title, "url": "/tasks", "subtitle": t.status, "icon": "check"})
    except Exception:
        pass
    try:
        for p in Project.query.filter(Project.name.ilike(f"%{q}%")).limit(5).all():
            results.append({"type": "project", "title": p.name, "url": "/projects", "subtitle": p.status, "icon": "folder"})
    except Exception:
        pass
    try:
        for c in Client.query.filter(db.or_(Client.name.ilike(f"%{q}%"), Client.company.ilike(f"%{q}%"))).limit(5).all():
            results.append({"type": "client", "title": c.name, "subtitle": c.company or c.pipeline_stage, "url": "/clients", "icon": "users"})
    except Exception:
        pass
    return jsonify({"results": results[:20]})


@api_bp.route("/api/version")
def version():
    return jsonify({"version": APP_VERSION, "download_url": DOWNLOAD_URL})


@api_bp.route("/api/update/check")
def api_update_check():
    """Check if an update is available for the requesting client.

    Accepts ?v=X.X.X with the client's own installed version.
    Compares against the latest GitHub release (stored in latest_release),
    NOT the server's APP_VERSION — so clients on older installs will always
    see the update even when the server code is already at a newer version.
    """
    from services.updater import latest_release, _is_newer

    if not latest_release:
        return jsonify({"available": False})

    client_version = request.args.get("v", "").strip().lstrip("v")

    if client_version:
        if _is_newer(latest_release["version"], client_version):
            return jsonify({"available": True, "version": latest_release["version"]})
        return jsonify({"available": False})

    # Fallback (no version param sent): compare against server's own version
    if _is_newer(latest_release["version"], APP_VERSION):
        return jsonify({"available": True, "version": latest_release["version"]})
    return jsonify({"available": False})


@api_bp.route("/api/update/install", methods=["POST"])
def api_update_install():
    """Start the update installation process."""
    import threading
    from services.updater import install_status

    if install_status["state"] in ("downloading", "mounting", "installing"):
        return jsonify({"error": "Instalacion en curso", "status": install_status["state"]}), 409

    threading.Thread(target=_do_install, daemon=True).start()
    return jsonify({"started": True})


@api_bp.route("/api/update/install/status")
def api_update_install_status():
    """Return the current installation status."""
    from services.updater import install_status
    return jsonify(install_status)


@api_bp.route("/api/sync/version")
def api_sync_version():
    """Return the current sync version counter (for real-time UI refresh)."""
    from services.sync import sync_manager
    version = sync_manager.sync_version if sync_manager else 0
    return jsonify({"version": version})


def _do_install():
    """Download latest DMG and install — updates install_status at each step."""
    from services.updater import install_status, GITHUB_API, _get_app_path
    import urllib.request, tempfile, shutil, subprocess, os as _os

    try:
        install_status["state"] = "downloading"
        install_status["error"] = None

        # Fetch latest release info
        req = urllib.request.Request(GITHUB_API)
        req.add_header("User-Agent", "NodexAI-Panel")
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())

        # Find DMG asset
        download_url = None
        for asset in release.get("assets", []):
            if asset["name"].endswith(".dmg"):
                download_url = asset["browser_download_url"]
                break
        if not download_url:
            install_status.update({"state": "error", "error": "No se encontro DMG en la release"})
            return

        # Download
        tmp_dir = tempfile.mkdtemp(prefix="nodex_update_")
        dmg_path = _os.path.join(tmp_dir, "update.dmg")
        urllib.request.urlretrieve(download_url, dmg_path)
        if _os.path.getsize(dmg_path) < 1_000_000:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            install_status.update({"state": "error", "error": "DMG descargado es demasiado pequeno (corrupto?)"})
            return

        install_status["state"] = "mounting"

        # Mount
        mount_point = _os.path.join(tmp_dir, "mount")
        _os.makedirs(mount_point, exist_ok=True)
        result = subprocess.run(
            ["hdiutil", "attach", dmg_path, "-mountpoint", mount_point, "-nobrowse", "-quiet"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            install_status.update({"state": "error", "error": f"Error al montar DMG: {result.stderr}"})
            return

        # Find .app
        app_name = None
        for item in _os.listdir(mount_point):
            if item.endswith(".app"):
                app_name = item
                break
        if not app_name:
            subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            install_status.update({"state": "error", "error": "No se encontro .app dentro del DMG"})
            return

        install_status["state"] = "installing"

        # Install via detached script (to allow the app to be overwritten)
        source_app = _os.path.join(mount_point, app_name)
        target_app = _get_app_path()

        script = f'''#!/bin/bash
        sleep 2
        killall "NodexAI Panel" 2>/dev/null
        rm -rf "{target_app}"
        cp -a "{source_app}" "{target_app}"
        hdiutil detach "{mount_point}" -quiet
        rm -rf "{tmp_dir}"
        open "{target_app}"
        '''
        script_path = _os.path.join(tmp_dir, "install.sh")
        with open(script_path, "w") as f:
            f.write(script)
        _os.chmod(script_path, 0o755)

        subprocess.Popen([script_path], start_new_session=True)
        install_status.update({"state": "done", "error": None})

    except Exception as e:
        install_status.update({"state": "error", "error": str(e)})


# ═══════════════════════════════════════
# AUTH
# ═══════════════════════════════════════

@api_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    """Authenticate and receive an API token."""
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not user.active or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
    if not user.api_token:
        user.generate_api_token()
        db.session.commit()
    return jsonify({
        "token": user.api_token,
        "user": _user_dict(user),
    })


@api_bp.route("/api/auth/me")
@api_token_required
def api_me():
    return jsonify({"user": _user_dict(g.api_user)})


@api_bp.route("/api/auth/regenerate-token", methods=["POST"])
@api_token_required
def api_regenerate_token():
    token = g.api_user.generate_api_token()
    db.session.commit()
    return jsonify({"token": token})


@api_bp.route("/api/sync/now", methods=["POST"])
@api_token_required
def api_sync_now():
    """Force an immediate pull from the remote database."""
    from services.sync import pull_now
    try:
        pull_now()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════

@api_bp.route("/api/dashboard")
@api_token_required
def api_dashboard():
    today = date.today()
    m, y = today.month, today.year

    active_payments = Payment.query.filter_by(status="activo").all()
    monthly_cost = sum(
        p.amount if p.frequency == "mensual"
        else p.amount / 12 if p.frequency == "anual"
        else 0 for p in active_payments
    )
    month_incomes = Income.query.filter(
        Income.status == "cobrado",
        db.extract("month", Income.paid_date) == m,
        db.extract("year", Income.paid_date) == y,
    ).all()
    monthly_income = sum(i.amount for i in month_incomes)
    mrr = sum(i.amount for i in Income.query.filter_by(frequency="mensual", status="cobrado").all())

    return jsonify({
        "monthly_income": monthly_income,
        "monthly_cost": monthly_cost,
        "balance": monthly_income - monthly_cost,
        "mrr": mrr,
        "active_projects": Project.query.filter_by(status="activo").count(),
        "pending_tasks": Task.query.filter(Task.status.in_(["pendiente", "en_progreso"])).count(),
        "total_clients": Client.query.count(),
        "new_ideas": Idea.query.filter_by(status="nueva").count(),
    })


# ═══════════════════════════════════════
# PROJECTS
# ═══════════════════════════════════════

@api_bp.route("/api/projects")
@api_token_required
def api_projects():
    status = request.args.get("status")
    q = Project.query
    if status:
        q = q.filter_by(status=status)
    projects = q.order_by(Project.created_at.desc()).all()
    return jsonify({"projects": [_project_dict(p) for p in projects]})


@api_bp.route("/api/projects/<int:pid>")
@api_token_required
def api_project_detail(pid):
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    return jsonify({"project": _project_dict(p)})


@api_bp.route("/api/projects", methods=["POST"])
@api_token_required
def api_project_create():
    data = request.get_json(force=True)
    p = Project(
        name=data.get("name", "").strip(),
        client_name=data.get("client_name", ""),
        status=data.get("status", "activo"),
        type=data.get("type", "web"),
        budget=float(data.get("budget", 0)),
        progress=int(data.get("progress", 0)),
        description=data.get("description", ""),
    )
    if data.get("deadline"):
        p.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
    db.session.add(p)
    db.session.commit()
    return jsonify({"project": _project_dict(p)}), 201


@api_bp.route("/api/projects/<int:pid>", methods=["PUT"])
@api_token_required
def api_project_update(pid):
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    for k in ("name", "client_name", "status", "type", "description", "notes"):
        if k in data:
            setattr(p, k, data[k])
    if "budget" in data:
        p.budget = float(data["budget"])
    if "progress" in data:
        p.progress = int(data["progress"])
    if "deadline" in data:
        p.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date() if data["deadline"] else None
    db.session.commit()
    return jsonify({"project": _project_dict(p)})


@api_bp.route("/api/projects/<int:pid>", methods=["DELETE"])
@api_token_required
def api_project_delete(pid):
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


# ═══════════════════════════════════════
# TASKS
# ═══════════════════════════════════════

@api_bp.route("/api/tasks")
@api_token_required
def api_tasks():
    status = request.args.get("status")
    project_id = request.args.get("project_id")
    assigned_to = request.args.get("assigned_to")
    q = Task.query.options(joinedload(Task.assignee), joinedload(Task.project))
    if status:
        q = q.filter_by(status=status)
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    if assigned_to:
        q = q.filter_by(assigned_to=int(assigned_to))
    tasks = q.order_by(Task.kanban_order.asc(), Task.due_date.asc().nullslast()).all()
    return jsonify({"tasks": [_task_dict(t) for t in tasks]})


@api_bp.route("/api/tasks/<int:tid>")
@api_token_required
def api_task_detail(tid):
    t = Task.query.options(joinedload(Task.assignee), joinedload(Task.project)).get(tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    d = _task_dict(t)
    d["subtasks"] = [{"id": s.id, "title": s.title, "done": s.done} for s in t.subtasks.all()]
    return jsonify({"task": d})


@api_bp.route("/api/tasks", methods=["POST"])
@api_token_required
def api_task_create():
    data = request.get_json(force=True)
    t = Task(
        title=data.get("title", "").strip(),
        description=data.get("description", ""),
        priority=data.get("priority", "media"),
        status=data.get("status", "pendiente"),
        assigned_to=int(data["assigned_to"]) if data.get("assigned_to") else None,
        project_id=int(data["project_id"]) if data.get("project_id") else None,
        estimated_minutes=int(data.get("estimated_minutes", 0)),
    )
    if data.get("due_date"):
        t.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
    db.session.add(t)
    db.session.commit()
    return jsonify({"task": _task_dict(t)}), 201


@api_bp.route("/api/tasks/<int:tid>", methods=["PUT"])
@api_token_required
def api_task_update(tid):
    t = db.session.get(Task, tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    for k in ("title", "description", "priority", "status"):
        if k in data:
            setattr(t, k, data[k])
    if "assigned_to" in data:
        t.assigned_to = int(data["assigned_to"]) if data["assigned_to"] else None
    if "project_id" in data:
        t.project_id = int(data["project_id"]) if data["project_id"] else None
    if "estimated_minutes" in data:
        t.estimated_minutes = int(data["estimated_minutes"])
    if "due_date" in data:
        t.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date() if data["due_date"] else None
    if "kanban_order" in data:
        t.kanban_order = int(data["kanban_order"])
    db.session.commit()
    return jsonify({"task": _task_dict(t)})


@api_bp.route("/api/tasks/<int:tid>", methods=["DELETE"])
@api_token_required
def api_task_delete(tid):
    t = db.session.get(Task, tid)
    if not t:
        return jsonify({"error": "not found"}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


# ═══════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════

@api_bp.route("/api/clients")
@api_token_required
def api_clients():
    stage = request.args.get("stage")
    q = Client.query
    if stage:
        q = q.filter_by(pipeline_stage=stage)
    clients = q.order_by(Client.created_at.desc()).all()
    return jsonify({"clients": [_client_dict(c) for c in clients]})


@api_bp.route("/api/clients/<int:cid>")
@api_token_required
def api_client_detail(cid):
    c = db.session.get(Client, cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify({"client": _client_dict(c)})


@api_bp.route("/api/clients", methods=["POST"])
@api_token_required
def api_client_create():
    data = request.get_json(force=True)
    c = Client(
        name=data.get("name", "").strip(),
        company=data.get("company", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        address=data.get("address", ""),
        nif=data.get("nif", ""),
        tags=data.get("tags", ""),
        pipeline_stage=data.get("pipeline_stage", "lead"),
        source=data.get("source", ""),
        notes=data.get("notes", ""),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"client": _client_dict(c)}), 201


@api_bp.route("/api/clients/<int:cid>", methods=["PUT"])
@api_token_required
def api_client_update(cid):
    c = db.session.get(Client, cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    for k in ("name", "company", "email", "phone", "address", "nif", "tags", "pipeline_stage", "source", "notes"):
        if k in data:
            setattr(c, k, data[k])
    db.session.commit()
    return jsonify({"client": _client_dict(c)})


@api_bp.route("/api/clients/<int:cid>", methods=["DELETE"])
@api_token_required
def api_client_delete(cid):
    c = db.session.get(Client, cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


# ═══════════════════════════════════════
# INVOICES
# ═══════════════════════════════════════

@api_bp.route("/api/invoices")
@api_token_required
def api_invoices():
    status = request.args.get("status")
    q = Invoice.query.options(joinedload(Invoice.client), joinedload(Invoice.project))
    if status:
        q = q.filter_by(status=status)
    invoices = q.order_by(Invoice.created_at.desc()).all()
    return jsonify({"invoices": [_invoice_dict(i) for i in invoices]})


@api_bp.route("/api/invoices/<int:iid>")
@api_token_required
def api_invoice_detail(iid):
    i = Invoice.query.options(joinedload(Invoice.client), joinedload(Invoice.project)).get(iid)
    if not i:
        return jsonify({"error": "not found"}), 404
    d = _invoice_dict(i)
    d["items"] = json.loads(i.items) if i.items else []
    return jsonify({"invoice": d})


@api_bp.route("/api/invoices/<int:iid>/status", methods=["PUT"])
@api_token_required
def api_invoice_status(iid):
    i = db.session.get(Invoice, iid)
    if not i:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True)
    new_status = data.get("status")
    if new_status in ("borrador", "enviada", "cobrada", "vencida"):
        i.status = new_status
        if new_status == "cobrada":
            i.paid_date = date.today()
        db.session.commit()
    return jsonify({"invoice": _invoice_dict(i)})


# ═══════════════════════════════════════
# PAYMENTS & INCOMES
# ═══════════════════════════════════════

@api_bp.route("/api/payments")
@api_token_required
def api_payments():
    status = request.args.get("status")
    q = Payment.query
    if status:
        q = q.filter_by(status=status)
    payments = q.order_by(Payment.next_date.asc().nullslast()).all()
    return jsonify({"payments": [_payment_dict(p) for p in payments]})


@api_bp.route("/api/incomes")
@api_token_required
def api_incomes():
    status = request.args.get("status")
    q = Income.query
    if status:
        q = q.filter_by(status=status)
    incomes = q.order_by(Income.created_at.desc()).all()
    return jsonify({"incomes": [_income_dict(i) for i in incomes]})


# ═══════════════════════════════════════
# TIME TRACKING
# ═══════════════════════════════════════

@api_bp.route("/api/time-entries")
@api_token_required
def api_time_entries():
    user_id = request.args.get("user_id", g.api_user.id)
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    q = TimeEntry.query.filter_by(user_id=int(user_id))
    if date_from:
        q = q.filter(TimeEntry.date >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        q = q.filter(TimeEntry.date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    entries = q.order_by(TimeEntry.date.desc()).all()
    return jsonify({"entries": [_time_entry_dict(e) for e in entries]})


@api_bp.route("/api/time-entries", methods=["POST"])
@api_token_required
def api_time_entry_create():
    data = request.get_json(force=True)
    e = TimeEntry(
        user_id=g.api_user.id,
        description=data.get("description", ""),
        minutes=int(data.get("minutes", 0)),
        date=datetime.strptime(data["date"], "%Y-%m-%d").date() if data.get("date") else date.today(),
        project_id=int(data["project_id"]) if data.get("project_id") else None,
        task_id=int(data["task_id"]) if data.get("task_id") else None,
    )
    db.session.add(e)
    db.session.commit()
    return jsonify({"entry": _time_entry_dict(e)}), 201


@api_bp.route("/api/time-entries/<int:eid>", methods=["DELETE"])
@api_token_required
def api_time_entry_delete(eid):
    e = db.session.get(TimeEntry, eid)
    if not e:
        return jsonify({"error": "not found"}), 404
    db.session.delete(e)
    db.session.commit()
    return jsonify({"ok": True})


# ═══════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════

@api_bp.route("/api/notifications/push")
@api_token_required
def api_push_notifications():
    """Get unread notifications for push/polling from mobile."""
    notifs = (
        Notification.query
        .filter_by(user_id=g.api_user.id, read=False)
        .order_by(Notification.created_at.desc())
        .limit(50).all()
    )
    return jsonify({
        "count": len(notifs),
        "notifications": [{
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in notifs],
    })


@api_bp.route("/api/notifications/mark-read", methods=["POST"])
@api_token_required
def api_mark_notifications_read():
    data = request.get_json(force=True)
    ids = data.get("ids", [])
    if ids:
        Notification.query.filter(
            Notification.id.in_(ids),
            Notification.user_id == g.api_user.id
        ).update({"read": True}, synchronize_session="fetch")
    else:
        Notification.query.filter_by(user_id=g.api_user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


# ═══════════════════════════════════════
# IDEAS
# ═══════════════════════════════════════

@api_bp.route("/api/ideas")
@api_token_required
def api_ideas():
    ideas = Idea.query.order_by(Idea.votes.desc(), Idea.created_at.desc()).all()
    return jsonify({"ideas": [{
        "id": i.id,
        "title": i.title,
        "description": i.description,
        "category": i.category,
        "status": i.status,
        "votes": i.votes,
        "created_by": i.created_by,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    } for i in ideas]})


# ═══════════════════════════════════════
# SERIALIZERS
# ═══════════════════════════════════════

def _user_dict(u):
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "active": u.active,
    }


def _project_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "client_name": p.client_name,
        "status": p.status,
        "type": p.type,
        "budget": p.budget,
        "progress": p.progress,
        "deadline": p.deadline.isoformat() if p.deadline else None,
        "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _task_dict(t):
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "priority": t.priority,
        "status": t.status,
        "assigned_to": t.assigned_to,
        "assignee_name": t.assignee.name if t.assignee else None,
        "project_id": t.project_id,
        "project_name": t.project.name if t.project else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "estimated_minutes": t.estimated_minutes,
        "kanban_order": t.kanban_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _client_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "company": c.company,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "nif": c.nif,
        "tags": c.tags,
        "pipeline_stage": c.pipeline_stage,
        "source": c.source,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _invoice_dict(i):
    return {
        "id": i.id,
        "number": i.number,
        "client_id": i.client_id,
        "client_name": i.client.name if i.client else None,
        "project_id": i.project_id,
        "subtotal": i.subtotal,
        "tax_rate": i.tax_rate,
        "tax_amount": i.tax_amount,
        "total": i.total,
        "status": i.status,
        "issue_date": i.issue_date.isoformat() if i.issue_date else None,
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "paid_date": i.paid_date.isoformat() if i.paid_date else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _payment_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "amount": p.amount,
        "currency": p.currency,
        "frequency": p.frequency,
        "category": p.category,
        "status": p.status,
        "next_date": p.next_date.isoformat() if p.next_date else None,
        "notes": p.notes,
    }


def _income_dict(i):
    return {
        "id": i.id,
        "name": i.name,
        "client_name": i.client_name,
        "amount": i.amount,
        "currency": i.currency,
        "frequency": i.frequency,
        "category": i.category,
        "status": i.status,
        "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None,
        "paid_date": i.paid_date.isoformat() if i.paid_date else None,
    }


def _time_entry_dict(e):
    return {
        "id": e.id,
        "user_id": e.user_id,
        "description": e.description,
        "minutes": e.minutes,
        "date": e.date.isoformat() if e.date else None,
        "project_id": e.project_id,
        "task_id": e.task_id,
    }
