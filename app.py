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
        db.create_all()
        seed_data()

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

    for bp in [auth_bp, dashboard_bp, payments_bp, projects_bp, tools_bp,
               tasks_bp, ideas_bp, info_bp, activity_bp, users_bp, settings_bp,
               credentials_bp]:
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
    socio = User(name="Socio", email="socio@nodexai.es", role="editor")
    socio.set_password("nodex2024")
    db.session.add_all([alex, socio])
    db.session.flush()

    # Info empresa
    company = CompanyInfo(
        name="NodexAI",
        description="Soluciones de inteligencia artificial para empresas",
        email="info@nodexai.es",
        website="https://nodexai.es",
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

    # Herramientas
    tools = [
        Tool(name="Claude", url="https://claude.ai", category="ia",
             cost_monthly=20, description="Asistente IA de Anthropic", used_by="ambos"),
        Tool(name="GitHub", url="https://github.com", category="desarrollo",
             cost_monthly=0, description="Repositorios de codigo", used_by="ambos"),
        Tool(name="VSCode", url="https://code.visualstudio.com", category="desarrollo",
             cost_monthly=0, description="Editor de codigo", used_by="ambos"),
        Tool(name="Vercel", url="https://vercel.com", category="infraestructura",
             cost_monthly=0, description="Deploy de aplicaciones web", used_by="alex"),
        Tool(name="Discord", url="https://discord.com", category="comunicacion",
             cost_monthly=0, description="Comunicacion interna (a sustituir por este panel)", used_by="ambos"),
    ]
    db.session.add_all(tools)

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


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
