import secrets
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(200), default="")
    role = db.Column(db.String(20), default=ROLE_EDITOR)
    active = db.Column(db.Boolean, default=True, index=True)
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw, method="pbkdf2:sha256")

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def generate_api_token(self):
        self.api_token = secrets.token_hex(32)
        return self.api_token

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def has_permission(self, module, action="read"):
        perms = ROLE_PERMISSIONS.get(self.role, {})
        module_perms = perms.get(module, [])
        return action in module_perms


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default="EUR")
    frequency = db.Column(db.String(20), default="mensual")  # mensual, anual, unico
    category = db.Column(db.String(50), default="otro")  # herramienta, servidor, servicio, otro
    status = db.Column(db.String(20), default="activo")  # activo, cancelado, pendiente
    next_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    client_name = db.Column(db.String(200), default="")
    status = db.Column(db.String(20), default="activo")  # activo, pausado, completado, cancelado
    type = db.Column(db.String(30), default="web")  # web, app, bot, otro
    budget = db.Column(db.Float, default=0)
    progress = db.Column(db.Integer, default=0)
    deadline = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    industry = db.Column(db.String(100), default="")
    website = db.Column(db.String(300), default="")
    status = db.Column(db.String(30), default="por_escribir")  # por_escribir, contactada, en_espera, han_contestado, no_responden, en_negociacion, cerrada
    interest = db.Column(db.String(300), default="")  # nivel / area de interes de la empresa
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class CompanyContact(db.Model):
    __tablename__ = "company_contacts"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(100), default="")
    phone = db.Column(db.String(50), default="")
    email = db.Column(db.String(200), default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship("Company", foreign_keys=[company_id])


class ProjectContact(db.Model):
    __tablename__ = "project_contacts"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(100), default="")
    phone = db.Column(db.String(50), default="")
    email = db.Column(db.String(200), default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship("Project", foreign_keys=[project_id])


class Tool(db.Model):
    __tablename__ = "tools"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), default="")
    category = db.Column(db.String(50), default="otro")  # desarrollo, diseno, ia, infraestructura, comunicacion, otro
    cost_monthly = db.Column(db.Float, default=0)
    description = db.Column(db.Text, default="")
    used_by = db.Column(db.String(50), default="ambos")  # alex, socio, ambos
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    priority = db.Column(db.String(10), default="media")  # alta, media, baja
    status = db.Column(db.String(20), default="pendiente")  # pendiente, en_progreso, completada
    due_date = db.Column(db.Date, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    estimated_minutes = db.Column(db.Integer, default=0)  # tiempo estimado
    kanban_order = db.Column(db.Integer, default=0)  # orden en columna kanban
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    assignee = db.relationship("User", foreign_keys=[assigned_to])
    project = db.relationship("Project", foreign_keys=[project_id])
    company = db.relationship("Company", foreign_keys=[company_id])


class Idea(db.Model):
    __tablename__ = "ideas"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(30), default="feature")  # feature, proyecto, mejora, otro
    status = db.Column(db.String(20), default="nueva")  # nueva, evaluando, aprobada, descartada
    votes = db.Column(db.Integer, default=0)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship("User", foreign_keys=[created_by])
    project = db.relationship("Project", foreign_keys=[project_id])
    company = db.relationship("Company", foreign_keys=[company_id])


class Income(db.Model):
    __tablename__ = "incomes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    client_name = db.Column(db.String(200), default="")
    amount = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default="EUR")
    frequency = db.Column(db.String(20), default="unico")  # mensual, anual, unico
    category = db.Column(db.String(50), default="proyecto")  # proyecto, servicio, consultoria, otro
    status = db.Column(db.String(20), default="pendiente")  # cobrado, pendiente, facturado
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    invoice_date = db.Column(db.Date, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship("Project", foreign_keys=[project_id])


class Credential(db.Model):
    __tablename__ = "credentials"
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), default="")
    username = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    password = db.Column(db.String(500), default="")
    api_key = db.Column(db.String(500), default="")
    notes = db.Column(db.Text, default="")
    category = db.Column(db.String(50), default="otro")  # hosting, ia, dominio, desarrollo, email, otro
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class CompanyInfo(db.Model):
    __tablename__ = "company_info"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default="NodexAI")
    description = db.Column(db.Text, default="")
    phone = db.Column(db.String(30), default="")
    email = db.Column(db.String(120), default="")
    address = db.Column(db.String(200), default="")
    website = db.Column(db.String(200), default="")
    nif = db.Column(db.String(20), default="")
    founded = db.Column(db.String(10), default="")
    sector = db.Column(db.String(100), default="")
    linkedin = db.Column(db.String(200), default="")
    github = db.Column(db.String(200), default="")
    extra_info = db.Column(db.Text, default="")


class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50))
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel = db.Column(db.String(50), default="general")  # general, project_3, dm_1_2
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship("User", foreign_keys=[sender_id])


class CallSession(db.Model):
    __tablename__ = "call_sessions"
    id = db.Column(db.Integer, primary_key=True)
    room_name = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project", foreign_keys=[project_id])
    creator = db.relationship("User", foreign_keys=[created_by])


# ═══════════════════════════════════════
# ENTERPRISE MODELS (v1.4)
# ═══════════════════════════════════════

class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    address = db.Column(db.Text, default="")
    nif = db.Column(db.String(30), default="")
    tags = db.Column(db.String(300), default="")
    pipeline_stage = db.Column(db.String(30), default="lead")  # lead, propuesta, negociacion, cerrado, perdido
    source = db.Column(db.String(50), default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(30), default="info")  # message, task, payment, system
    title = db.Column(db.String(300), default="")
    body = db.Column(db.Text, default="")
    link = db.Column(db.String(300), default="")
    read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])


class TimeEntry(db.Model):
    __tablename__ = "time_entries"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    description = db.Column(db.String(300), default="")
    minutes = db.Column(db.Integer, default=0)
    date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])
    task = db.relationship("Task", foreign_keys=[task_id])
    project = db.relationship("Project", foreign_keys=[project_id])


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    items = db.Column(db.Text, default="[]")  # JSON: [{description, qty, unit_price}]
    subtotal = db.Column(db.Float, default=0)
    tax_rate = db.Column(db.Float, default=21)  # IVA %
    tax_amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default="borrador")  # borrador, enviada, cobrada, vencida
    issue_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    due_date = db.Column(db.Date, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    client = db.relationship("Client", foreign_keys=[client_id])
    project = db.relationship("Project", foreign_keys=[project_id])


class Subtask(db.Model):
    __tablename__ = "subtasks"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    task = db.relationship("Task", backref=db.backref("subtasks", lazy="dynamic", cascade="all, delete-orphan"))


class Document(db.Model):
    __tablename__ = "documents"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(500), default="")
    file_path = db.Column(db.String(500), default="")
    file_size = db.Column(db.Integer, default=0)  # bytes
    mime_type = db.Column(db.String(100), default="")
    category = db.Column(db.String(50), default="otro")  # contrato, factura, propuesta, informe, plantilla, otro
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship("Project", foreign_keys=[project_id])
    client = db.relationship("Client", foreign_keys=[client_id])
    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class Resource(db.Model):
    __tablename__ = "resources"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(500), default="")
    file_path = db.Column(db.String(500), default="")
    file_size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100), default="")
    category = db.Column(db.String(50), default="otro")  # logo, presentacion, brand, plantilla, otro
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class Automation(db.Model):
    __tablename__ = "automations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    trigger_type = db.Column(db.String(50), default="event")  # event, schedule, manual
    trigger_config = db.Column(db.Text, default="{}")  # JSON config
    action_type = db.Column(db.String(50), default="notify")  # notify, create_task, update_status, email
    action_config = db.Column(db.Text, default="{}")  # JSON config
    active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    run_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])


# ═══════════════════════════════════════
# PERMISSIONS (v2.0)
# ═══════════════════════════════════════

MODULES = [
    "dashboard", "pagos", "ingresos", "clientes", "proyectos",
    "tareas", "herramientas", "ideas", "cowork", "credenciales",
    "facturas", "timetracking", "calendario", "documentos",
    "reportes", "automatizaciones", "usuarios", "configuracion",
]

# Roles: admin has all, editor has most, viewer is read-only
ROLE_PERMISSIONS = {
    "admin": {m: ["read", "write", "delete", "admin"] for m in MODULES},
    "editor": {m: ["read", "write"] for m in MODULES},
    "viewer": {m: ["read"] for m in MODULES},
}

