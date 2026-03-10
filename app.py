import os
from datetime import datetime, timezone, date, timedelta
from flask import Flask, g
from config import Config, BASE_DIR
from models import db, User, Payment, Project, Tool, Task, Idea, Credential, CompanyInfo


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        # Only run migrations/seeding if explicitly requested or on the Railway server
        # This prevents the desktop app from making 200+ slow remote DB queries on startup
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RUN_MIGRATIONS"):
            db.create_all()
            seed_data()
            sync_tools()

    # Blueprints
    from routes.auth import auth_bp, _load_current_user
    from routes.dashboard import dashboard_bp
    from routes.payments import payments_bp
    from routes.projects import projects_bp
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

    for bp in [auth_bp, dashboard_bp, payments_bp, incomes_bp, projects_bp,
               tools_bp, tasks_bp, ideas_bp, info_bp, activity_bp, users_bp,
               settings_bp, credentials_bp, cowork_bp, api_bp]:
        app.register_blueprint(bp)

    @app.before_request
    def before_request():
        _load_current_user()

    @app.context_processor
    def inject_user():
        return {"current_user": g.get("user")}

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
