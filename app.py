import os
import logging
from datetime import datetime, timezone, date, timedelta
from flask import Flask, g
from config import Config, BASE_DIR, REMOTE_DATABASE_URL, APP_VERSION, HOSTED_MODE
from models import db, User, Payment, Project, Tool, Task, Idea, Credential, CompanyInfo, CalendarEvent, PushToken

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
log = logging.getLogger("app")


MIGRATIONS = [
    ("users", "api_token", "VARCHAR(64)"),
    ("tasks", "estimated_minutes", "INTEGER DEFAULT 0"),
    ("tasks", "kanban_order", "INTEGER DEFAULT 0"),
    ("tasks", "company_id", "INTEGER"),
    ("tasks", "recurrence", "VARCHAR(20) DEFAULT 'ninguna'"),
    ("tasks", "reminder_minutes", "INTEGER"),
    ("tasks", "last_notified_at", "TIMESTAMP"),
    ("ideas", "company_id", "INTEGER"),
    ("companies", "interest", "VARCHAR(300) DEFAULT ''"),
    ("companies", "problem", "TEXT DEFAULT ''"),
    ("companies", "solution", "TEXT DEFAULT ''"),
    ("projects", "company_id", "INTEGER"),
]


def _auto_migrate(app):
    """Add missing columns to existing SQLite tables (safe, idempotent)."""
    import sqlite3, re
    _ident_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    for table, column, col_type in MIGRATIONS:
        if not (_ident_re.match(table) and _ident_re.match(column)):
            log.warning(f"Skipping invalid migration identifier: {table}.{column}")
            continue
        c.execute(f'PRAGMA table_info("{table}")')
        existing = [row[1] for row in c.fetchall()]
        if column not in existing:
            c.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type}')
            log.info(f"Migration: added {table}.{column}")

    conn.commit()
    conn.close()


def _auto_migrate_pg():
    """Add missing columns and fix sequences in PostgreSQL (safe, idempotent)."""
    from sqlalchemy import text
    import re

    # Whitelist pattern: only allow safe identifier characters
    _ident_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    conn = db.engine.connect()
    # 1. Add missing columns
    for table, column, col_type in MIGRATIONS:
        if not (_ident_re.match(table) and _ident_re.match(column)):
            log.warning(f"Skipping invalid migration identifier: {table}.{column}")
            continue
        try:
            conn.execute(text(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {col_type}'
            ))
            conn.commit()
        except Exception:
            conn.rollback()
    # 2. Fix auto-increment sequences (sync inserts rows with explicit IDs,
    #    leaving the sequence behind, causing duplicate key errors on INSERT)
    try:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )).fetchall()
        for (tbl,) in tables:
            if not _ident_re.match(tbl):
                continue
            try:
                conn.execute(text(
                    f'SELECT setval(pg_get_serial_sequence(\'{tbl}\', \'id\'), '
                    f'COALESCE((SELECT MAX(id) FROM "{tbl}"), 1))'
                ))
                conn.commit()
            except Exception:
                conn.rollback()
    except Exception:
        conn.rollback()
    conn.close()
    log.info("PostgreSQL migration + sequence fix complete")


def _migrate_task_assignments():
    """One-time: copy legacy assigned_to into task_assignments table."""
    from models import Task, TaskAssignment
    tasks_with_assignee = Task.query.filter(Task.assigned_to.isnot(None)).all()
    for t in tasks_with_assignee:
        existing = TaskAssignment.query.filter_by(task_id=t.id, user_id=t.assigned_to).first()
        if not existing:
            db.session.add(TaskAssignment(task_id=t.id, user_id=t.assigned_to))
    db.session.commit()


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    app.config.from_object(Config)
    app.config["APP_VERSION"] = APP_VERSION
    db.init_app(app)

    with app.app_context():
        db.create_all()

        if HOSTED_MODE:
            log.info("Hosted mode — using PostgreSQL directly, sync disabled")
            _auto_migrate_pg()
        else:
            # Auto-migrate: add missing columns to existing SQLite tables
            _auto_migrate(app)

            # Migrate legacy assigned_to → task_assignments (one-time)
            _migrate_task_assignments()

            # Start background sync from Railway PostgreSQL
            from services.sync import SyncManager, sync_manager
            import services.sync as sync_mod
            mgr = SyncManager(
                local_url=Config.SQLALCHEMY_DATABASE_URI,
                remote_url=REMOTE_DATABASE_URL,
            )
            sync_mod.sync_manager = mgr
            mgr.start()

            # If local DB is empty, wait briefly for first sync to populate it
            if not User.query.first():
                log.info("Local DB empty — waiting for first sync...")
                mgr.wait_first_sync(timeout=10)

    # Initialize FCM for push notifications
    from services.push import init_fcm
    init_fcm()

    # Blueprints
    from routes.auth import auth_bp, _load_current_user
    from routes.dashboard import dashboard_bp
    from routes.payments import payments_bp
    from routes.projects import projects_bp
    from routes.companies import companies_bp
    from routes.tools import tools_bp
    from routes.tasks import tasks_bp
    from routes.ideas import ideas_bp
    from routes.info import info_bp
    from routes.activity import activity_bp
    from routes.users import users_bp
    from routes.settings import settings_bp
    from routes.credentials import credentials_bp
    from routes.incomes import incomes_bp
    from routes.cowork import cowork_bp
    from routes.api import api_bp
    from routes.notifications import notifications_bp
    from routes.clients import clients_bp
    # Enterprise v2.0
    from routes.invoices import invoices_bp
    from routes.balance import balance_bp
    from routes.timetracking import timetracking_bp
    from routes.calendar import calendar_bp
    from routes.documents import documents_bp
    from routes.reports import reports_bp
    from routes.automations import automations_bp
    from routes.ai_assistant import ai_bp
    from routes.resources import resources_bp
    from routes.captacion import captacion_bp

    for bp in [auth_bp, dashboard_bp, payments_bp, incomes_bp, companies_bp, projects_bp,
               tools_bp, tasks_bp, ideas_bp, info_bp, activity_bp, users_bp,
               settings_bp, credentials_bp, cowork_bp, api_bp, notifications_bp,
               clients_bp,
               # Enterprise v2.0
               invoices_bp, balance_bp, timetracking_bp, calendar_bp,
               documents_bp, reports_bp, automations_bp, ai_bp, resources_bp,
               captacion_bp]:
        app.register_blueprint(bp)

    @app.before_request
    def before_request():
        _load_current_user()

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if HOSTED_MODE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.context_processor
    def inject_globals():
        user = g.get("user")
        notif_count = 0
        if user:
            from services.notifications import get_unread_count
            notif_count = get_unread_count(user.id)
        from services.updater import update_available
        return {
            "current_user": user,
            "notif_count": notif_count,
            "update_available": update_available,
        }

    return app


def seed_data():
    if User.query.first():
        return

    # Usuarios
    alex = User(name="Alex", email="torres.diez.alex@gmail.com", role="admin")
    alex.set_password("nodex2024")
    socio = User(name="Socio", email="socio@nodexai.es", role="admin")
    socio.set_password("nodex2024")
    db.session.add_all([alex, socio])
    db.session.flush()

    # Info empresa
    company = CompanyInfo(
        name="NodexAI",
        description="Soluciones de inteligencia artificial para empresas",
        email="info@nodexai.es",
        website="https://nodexai.es",
        sector="Tecnologia / Inteligencia Artificial",
        founded="2024",
        github="https://github.com/alextorres1709",
    )
    db.session.add(company)

    # Pagos reales
    payments = [
        Payment(name="Claude Pro", amount=20, currency="EUR", frequency="mensual",
                category="herramienta", status="activo",
                next_date=date.today().replace(day=1) + timedelta(days=32),
                notes="Plan Pro de Anthropic"),
        Payment(name="Dominio nodexai.es", amount=12, currency="EUR", frequency="anual",
                category="servicio", status="activo", notes="Renovacion anual"),
    ]
    db.session.add_all(payments)

    # Proyectos
    projects = [
        Project(name="Panel NodexAI", client_name="Interno", status="activo",
                type="web", progress=30, description="Panel interno de gestion"),
        Project(name="Web NodexAI", client_name="Interno", status="activo",
                type="web", progress=60, description="Pagina web corporativa"),
    ]
    db.session.add_all(projects)
    db.session.flush()

    # Tareas
    tasks = [
        Task(title="Terminar panel interno", priority="alta", status="en_progreso",
             assigned_to=alex.id, project_id=projects[0].id,
             due_date=date.today() + timedelta(days=7)),
        Task(title="Compartir codigo con socio", priority="media", status="pendiente",
             assigned_to=alex.id,
             description="Configurar acceso seguro al repositorio"),
        Task(title="Configurar dominio email", priority="media", status="pendiente",
             assigned_to=alex.id),
    ]
    db.session.add_all(tasks)

    # Ideas
    ideas = [
        Idea(title="Bot WhatsApp para clientes", category="feature", status="nueva",
             description="Bot automatizado de atencion al cliente via WhatsApp",
             created_by=alex.id, votes=1),
        Idea(title="Dashboard de analytics para clientes", category="proyecto",
             status="evaluando", description="Panel donde los clientes ven sus metricas",
             created_by=alex.id),
    ]
    db.session.add_all(ideas)

    db.session.commit()


# List of all tools - used by both seed_data and sync_tools
TOOLS_LIST = [
    {"name": "Claude", "url": "https://claude.ai", "category": "ia",
     "cost_monthly": 20, "description": "Asistente IA de Anthropic", "used_by": "ambos"},
    {"name": "GitHub", "url": "https://github.com", "category": "desarrollo",
     "cost_monthly": 0, "description": "Repositorios de codigo", "used_by": "ambos"},
    {"name": "VSCode", "url": "https://code.visualstudio.com", "category": "desarrollo",
     "cost_monthly": 0, "description": "Editor de codigo", "used_by": "ambos"},
    {"name": "Vercel", "url": "https://vercel.com", "category": "infraestructura",
     "cost_monthly": 0, "description": "Deploy de aplicaciones web", "used_by": "alex"},
    {"name": "Discord", "url": "https://discord.com", "category": "comunicacion",
     "cost_monthly": 0, "description": "Comunicacion interna (a sustituir por este panel)", "used_by": "ambos"},
    {"name": "Supabase", "url": "https://supabase.com", "category": "infraestructura",
     "cost_monthly": 0, "description": "Base de datos PostgreSQL (inmobiliaria, madness)", "used_by": "ambos"},
    {"name": "Railway", "url": "https://railway.app", "category": "infraestructura",
     "cost_monthly": 5, "description": "Deploy del panel y n8n", "used_by": "alex"},
    {"name": "n8n", "url": "https://n8n.io", "category": "desarrollo",
     "cost_monthly": 0, "description": "Automatizaciones (self-hosted en Railway)", "used_by": "ambos"},
    {"name": "Antigravity", "url": "https://antigravity.dev", "category": "desarrollo",
     "cost_monthly": 0, "description": "IDE con extension Claude Code", "used_by": "ambos"},
    {"name": "Claude Code", "url": "https://claude.ai/code", "category": "ia",
     "cost_monthly": 0, "description": "Extension de programacion IA para el IDE", "used_by": "ambos"},
]


def sync_tools():
    """Add missing tools on every startup. Does not modify existing ones."""
    existing = {t.name for t in Tool.query.all()}
    added = 0
    for t in TOOLS_LIST:
        if t["name"] not in existing:
            db.session.add(Tool(**t))
            added += 1
    if added:
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
