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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw, method="pbkdf2:sha256")

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN


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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    assignee = db.relationship("User", foreign_keys=[assigned_to])
    project = db.relationship("Project", foreign_keys=[project_id])


class Idea(db.Model):
    __tablename__ = "ideas"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(30), default="feature")  # feature, proyecto, mejora, otro
    status = db.Column(db.String(20), default="nueva")  # nueva, evaluando, aprobada, descartada
    votes = db.Column(db.Integer, default=0)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship("User", foreign_keys=[created_by])
    project = db.relationship("Project", foreign_keys=[project_id])


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
