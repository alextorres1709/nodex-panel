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
    totp_secret = db.Column(db.String(64), nullable=True)  # base32 secret for 2FA
    totp_enabled = db.Column(db.Boolean, default=False)
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
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True, index=True)
    status = db.Column(db.String(20), default="activo")  # activo, pausado, completado, cancelado
    type = db.Column(db.String(30), default="web")  # web, app, bot, otro
    budget = db.Column(db.Float, default=0)
    progress = db.Column(db.Integer, default=0)
    deadline = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship("Company", foreign_keys=[company_id])
    lead = db.relationship("Lead", foreign_keys=[lead_id])


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    industry = db.Column(db.String(100), default="")
    website = db.Column(db.String(300), default="")
    status = db.Column(db.String(30), default="por_escribir")  # por_escribir, contactada_sin_respuesta, interesado, llamada_agendada, demo_preparacion, demo_realizada, propuesta_enviada, negociacion, cerrado_ganado, cerrado_perdido, pago_recibido, welcome_enviado, en_implementacion, entregado, seguimiento
    interest = db.Column(db.String(300), default="")  # nivel / area de interes de la empresa
    problem = db.Column(db.Text, default="")  # problema detectado en la empresa
    solution = db.Column(db.Text, default="")  # soluciones que podemos ofrecer
    notes = db.Column(db.Text, default="")
    # ─── Lead-like fields (CRM B2B) ───
    priority = db.Column(db.String(10), default="media")  # alta, media, baja
    next_contact_date = db.Column(db.Date, nullable=True, index=True)
    source = db.Column(db.String(100), default="")  # apollo, linkedin, referido, web, evento...
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    phone = db.Column(db.String(50), default="")  # teléfono principal de la empresa (centralita)
    email = db.Column(db.String(200), default="")  # email genérico (info@/contacto@)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    assignee = db.relationship("User", foreign_keys=[assigned_to])


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


# ═══════════════════════════════════════════
# EMAIL TEMPLATES (Apollo-style outbound CRM)
# ═══════════════════════════════════════════

EMAIL_TEMPLATE_CATEGORIES = [
    ("intro", "Presentación inicial"),
    ("follow_up", "Follow-up"),
    ("value", "Aportar valor"),
    ("meeting", "Solicitud de reunión"),
    ("breakup", "Break-up / cierre"),
    ("other", "Otro"),
]


class EmailTemplate(db.Model):
    __tablename__ = "email_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(30), default="intro")  # intro, follow_up, value, meeting, breakup, other
    step_order = db.Column(db.Integer, default=1)  # posición en la secuencia
    subject = db.Column(db.String(300), default="")
    body = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════
# COMPANY INTERACTIONS — timeline of emails/calls/meetings/notes
# ═══════════════════════════════════════════

INTERACTION_TYPES = [
    ("email", "Email"),
    ("call", "Llamada"),
    ("meeting", "Reunión"),
    ("note", "Nota"),
]

INTERACTION_STATUSES = [
    ("queued", "En cola"),       # email esperando a n8n
    ("sent", "Enviado"),
    ("done", "Hecho"),           # llamadas/reuniones completadas
    ("failed", "Fallido"),
]


class CompanyInteraction(db.Model):
    __tablename__ = "company_interactions"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("company_contacts.id"), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # quién registró
    type = db.Column(db.String(20), nullable=False, default="note")  # email, call, meeting, note
    status = db.Column(db.String(20), default="done")  # queued, sent, done, failed
    subject = db.Column(db.String(300), default="")
    body = db.Column(db.Text, default="")
    to_email = db.Column(db.String(200), default="")  # solo emails
    template_id = db.Column(db.Integer, db.ForeignKey("email_templates.id"), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)  # cuando n8n confirma envío
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    company = db.relationship("Company", foreign_keys=[company_id])
    contact = db.relationship("CompanyContact", foreign_keys=[contact_id])
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    user = db.relationship("User", foreign_keys=[user_id])
    template = db.relationship("EmailTemplate", foreign_keys=[template_id])


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


REMINDER_CHOICES = [
    (0, "Sin recordatorio"),
    (30, "Cada 30 min"),
    (60, "Cada hora"),
    (120, "Cada 2 horas"),
    (240, "Cada 4 horas"),
    (480, "Cada 8 horas"),
    (1440, "Cada dia"),
]


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # legacy, kept for compat
    priority = db.Column(db.String(10), default="media")  # alta, media, baja
    status = db.Column(db.String(20), default="pendiente")  # pendiente, en_progreso, completada
    due_date = db.Column(db.Date, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    estimated_minutes = db.Column(db.Integer, default=0)  # tiempo estimado
    kanban_order = db.Column(db.Integer, default=0)  # orden en columna kanban
    recurrence = db.Column(db.String(20), default="ninguna")  # ninguna, semanal, anual
    reminder_minutes = db.Column(db.Integer, default=0)  # 0=off, 30/60/120/240/480/1440
    last_notified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    assignee = db.relationship("User", foreign_keys=[assigned_to])
    assignees = db.relationship("User", secondary="task_assignments", backref="assigned_tasks")
    project = db.relationship("Project", foreign_keys=[project_id])
    company = db.relationship("Company", foreign_keys=[company_id])

    @property
    def safe_due_date(self):
        if not self.due_date:
            return None
        try:
            from datetime import date, datetime
            if isinstance(self.due_date, datetime):
                return self.due_date.date()
            if isinstance(self.due_date, date):
                return self.due_date
            if isinstance(self.due_date, str):
                return datetime.strptime(str(self.due_date).split("T")[0].split(" ")[0], "%Y-%m-%d").date()
            return None
        except Exception:
            return None


class TaskAssignment(db.Model):
    __tablename__ = "task_assignments"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


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


class Objective(db.Model):
    __tablename__ = "objectives"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="nuevo")  # nuevo, en_progreso, completado, archivado
    priority = db.Column(db.String(10), default="media")  # alta, media, baja
    progress = db.Column(db.Integer, default=0)  # 0-100
    target_date = db.Column(db.Date, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    assignee = db.relationship("User", foreign_keys=[assigned_to])
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
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)  # legacy
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True, index=True)
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
    lead = db.relationship("Lead", foreign_keys=[lead_id])
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
    drive_file_id = db.Column(db.String(100), default="")
    file_size = db.Column(db.Integer, default=0)  # bytes
    mime_type = db.Column(db.String(100), default="")
    category = db.Column(db.String(50), default="otro")  # contrato, factura_pago, factura_ingreso, propuesta, informe, plantilla, otro
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id"), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    project = db.relationship("Project", foreign_keys=[project_id])
    client = db.relationship("Client", foreign_keys=[client_id])
    company = db.relationship("Company", foreign_keys=[company_id])
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    task = db.relationship("Task", foreign_keys=[task_id])
    idea = db.relationship("Idea", foreign_keys=[idea_id])
    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class Resource(db.Model):
    __tablename__ = "resources"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(500), default="")
    file_path = db.Column(db.String(500), default="")
    drive_file_id = db.Column(db.String(100), default="")
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
# CALENDAR EVENTS
# ═══════════════════════════════════════

class CalendarEvent(db.Model):
    __tablename__ = "calendar_events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    event_type = db.Column(db.String(20), default="evento")  # reunion, evento, recordatorio
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=True)  # "HH:MM"
    end_time = db.Column(db.String(5), nullable=True)    # "HH:MM"
    location = db.Column(db.String(300), default="")
    color = db.Column(db.String(7), default="#6366f1")
    all_day = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    gcal_event_id = db.Column(db.String(200), nullable=True)  # Google Calendar event ID
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])
    assignee = db.relationship("User", foreign_keys=[assigned_to])


# ═══════════════════════════════════════
# GOOGLE OAUTH2 TOKENS (Google Calendar)
# ═══════════════════════════════════════

class GoogleOAuthToken(db.Model):
    __tablename__ = "google_oauth_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    token_json = db.Column(db.Text, nullable=False)  # JSON with access/refresh tokens
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])


# ═══════════════════════════════════════
# PUSH TOKENS (FCM)
# ═══════════════════════════════════════

class PushToken(db.Model):
    __tablename__ = "push_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.Text, nullable=False, unique=True)
    platform = db.Column(db.String(20), default="android")  # android, ios, web
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])


# ═══════════════════════════════════════
# COMMENTS (v2.1) — comentarios en tareas con menciones
# ═══════════════════════════════════════

class TaskComment(db.Model):
    __tablename__ = "task_comments"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship("User", foreign_keys=[author_id])
    task = db.relationship("Task", backref=db.backref("comments", lazy="dynamic", cascade="all, delete-orphan"))


# ═══════════════════════════════════════
# PROJECT TEMPLATES (v2.1)
# ═══════════════════════════════════════

class ProjectTemplate(db.Model):
    __tablename__ = "project_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    type = db.Column(db.String(30), default="web")
    default_status = db.Column(db.String(20), default="activo")
    default_progress = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])


class ProjectTemplateTask(db.Model):
    __tablename__ = "project_template_tasks"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("project_templates.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    priority = db.Column(db.String(10), default="media")
    estimated_minutes = db.Column(db.Integer, default=0)
    days_offset = db.Column(db.Integer, default=0)  # due_date relative to project start
    sort_order = db.Column(db.Integer, default=0)

    template = db.relationship("ProjectTemplate", backref=db.backref("template_tasks", lazy="dynamic", cascade="all, delete-orphan"))


# ═══════════════════════════════════════
# OBJECTIVE SNAPSHOTS (v2.1) — historial de progreso para gráfico OKR
# ═══════════════════════════════════════

class ObjectiveSnapshot(db.Model):
    __tablename__ = "objective_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    objective_id = db.Column(db.Integer, db.ForeignKey("objectives.id"), nullable=False, index=True)
    progress = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    objective = db.relationship("Objective", backref=db.backref("snapshots", lazy="dynamic", cascade="all, delete-orphan"))


# ═══════════════════════════════════════
# PERMISSIONS (v2.0)
# ═══════════════════════════════════════

# ═══════════════════════════════════════
# GCAL ITEM SYNC — maps tasks/payments/projects/invoices to GCal event IDs
# New table: created automatically by db.create_all() on startup.
# ═══════════════════════════════════════

class GcalItemSync(db.Model):
    __tablename__ = "gcal_item_sync"
    id = db.Column(db.Integer, primary_key=True)
    item_type = db.Column(db.String(20), nullable=False)   # task|payment|project|invoice
    item_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    gcal_event_id = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("item_type", "item_id", "user_id", name="uq_gcal_item"),
    )


# ═══════════════════════════════════════════════════════════════
# LEADS — personas/contactos comerciales (Apollo-style)
# Un Lead pertenece opcionalmente a una Company (Empresa a contactar).
# Status transita: nuevo → contactado → interesado → qualified →
# propuesta → negociacion → cliente / perdido.
# Cuando status == "cliente" el Lead reemplaza al antiguo modelo
# Client (la sección "Clientes" del nav desaparece).
# ═══════════════════════════════════════════════════════════════

LEAD_STATUSES = [
    ("nuevo", "Nuevo"),
    ("contactado", "Contactado"),
    ("interesado", "Interesado"),
    ("qualified", "Cualificado"),
    ("propuesta", "Propuesta"),
    ("negociacion", "Negociación"),
    ("cliente", "Cliente"),
    ("perdido", "Perdido"),
]


class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), default="")
    last_name = db.Column(db.String(120), default="")
    email = db.Column(db.String(200), default="", index=True)
    phone = db.Column(db.String(50), default="")
    position = db.Column(db.String(150), default="")
    linkedin = db.Column(db.String(300), default="")
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    company_name_cached = db.Column(db.String(200), default="")  # si no se enlaza a una company
    status = db.Column(db.String(30), default="nuevo", index=True)
    priority = db.Column(db.String(10), default="media")  # alta, media, baja
    source = db.Column(db.String(100), default="")  # apollo, linkedin, referido, web, evento...
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    next_contact_date = db.Column(db.Date, nullable=True, index=True)
    notes = db.Column(db.Text, default="")
    tags = db.Column(db.String(300), default="")
    converted_at = db.Column(db.DateTime, nullable=True)  # cuando pasó a cliente
    lost_reason = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    company = db.relationship("Company", foreign_keys=[company_id])
    assignee = db.relationship("User", foreign_keys=[assigned_to])

    @property
    def full_name(self):
        n = (self.first_name or "").strip() + " " + (self.last_name or "").strip()
        return n.strip() or self.email or "(sin nombre)"

    @property
    def display_company(self):
        if self.company_id and self.company:
            return self.company.name
        return self.company_name_cached or ""

    @property
    def is_client(self):
        return self.status == "cliente"


# ═══════════════════════════════════════════════════════════════
# SECUENCIAS (Apollo-style cadences) — listas de pasos email/call/wait
# que se ejecutan automáticamente sobre Leads inscritos.
# El scheduler (n8n) lee enrollments con next_run_at <= now().
# ═══════════════════════════════════════════════════════════════

class Sequence(db.Model):
    __tablename__ = "sequences"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])


SEQUENCE_STEP_TYPES = [
    ("email", "Email automático"),
    ("call", "Tarea de llamada"),
    ("manual", "Tarea manual"),
    ("wait", "Esperar (días)"),
]


class SequenceStep(db.Model):
    __tablename__ = "sequence_steps"
    id = db.Column(db.Integer, primary_key=True)
    sequence_id = db.Column(db.Integer, db.ForeignKey("sequences.id"), nullable=False, index=True)
    step_order = db.Column(db.Integer, default=1, index=True)
    step_type = db.Column(db.String(20), default="email")  # email, call, manual, wait
    wait_days = db.Column(db.Integer, default=0)  # días a esperar ANTES de ejecutar este paso
    template_id = db.Column(db.Integer, db.ForeignKey("email_templates.id"), nullable=True)
    subject = db.Column(db.String(300), default="")  # override si no hay template
    body = db.Column(db.Text, default="")
    task_title = db.Column(db.String(300), default="")  # para call/manual
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sequence = db.relationship(
        "Sequence",
        backref=db.backref(
            "steps", lazy="dynamic",
            cascade="all, delete-orphan",
            order_by="SequenceStep.step_order",
        ),
    )
    template = db.relationship("EmailTemplate", foreign_keys=[template_id])


SEQUENCE_ENROLL_STATUSES = [
    ("active", "Activo"),
    ("paused", "Pausado"),
    ("finished", "Finalizado"),
    ("cancelled", "Cancelado"),
]


class SequenceEnrollment(db.Model):
    __tablename__ = "sequence_enrollments"
    id = db.Column(db.Integer, primary_key=True)
    sequence_id = db.Column(db.Integer, db.ForeignKey("sequences.id"), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    current_step = db.Column(db.Integer, default=0)  # índice del próximo paso a ejecutar (0-based)
    next_run_at = db.Column(db.DateTime, nullable=True, index=True)  # cuando el scheduler debe ejecutar el próximo paso
    status = db.Column(db.String(20), default="active", index=True)  # active, paused, finished, cancelled
    enrolled_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    last_step_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sequence = db.relationship("Sequence", foreign_keys=[sequence_id])
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    enroller = db.relationship("User", foreign_keys=[enrolled_by])


# ═══════════════════════════════════════════════════════════════
# LEAD INTERACTIONS — timeline unificado por lead (emails/llamadas/notas)
# Análogo a CompanyInteraction pero anclado al Lead.
# ═══════════════════════════════════════════════════════════════

class LeadInteraction(db.Model):
    __tablename__ = "lead_interactions"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("sequence_enrollments.id"), nullable=True)
    step_id = db.Column(db.Integer, db.ForeignKey("sequence_steps.id"), nullable=True)
    type = db.Column(db.String(20), nullable=False, default="note")  # email, call, meeting, note, status_change
    status = db.Column(db.String(20), default="done")  # queued, sent, done, failed
    subject = db.Column(db.String(300), default="")
    body = db.Column(db.Text, default="")
    to_email = db.Column(db.String(200), default="")
    template_id = db.Column(db.Integer, db.ForeignKey("email_templates.id"), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    lead = db.relationship("Lead", foreign_keys=[lead_id])
    user = db.relationship("User", foreign_keys=[user_id])
    template = db.relationship("EmailTemplate", foreign_keys=[template_id])


MODULES = [
    "dashboard", "pagos", "ingresos", "leads", "proyectos",
    "tareas", "herramientas", "ideas", "cowork", "credenciales",
    "facturas", "timetracking", "calendario", "documentos",
    "reportes", "automatizaciones", "usuarios", "configuracion",
    "objetivos", "secuencias",
]

# Roles: admin has all, editor has most, viewer is read-only
ROLE_PERMISSIONS = {
    "admin": {m: ["read", "write", "delete", "admin"] for m in MODULES},
    "editor": {m: ["read", "write"] for m in MODULES},
    "viewer": {m: ["read"] for m in MODULES},
}

