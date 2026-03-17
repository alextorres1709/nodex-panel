import os
import sys
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_base_dir():
    """Return the directory containing templates/static."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _get_local_db_path():
    """Return path to the local SQLite database."""
    if getattr(sys, "frozen", False):
        # Packaged app: ~/Library/Application Support/NodexAI/
        data_dir = os.path.join(os.path.expanduser("~"), "Library",
                                "Application Support", "NodexAI")
    else:
        # Development: project directory
        data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "panel.db")


BASE_DIR = _get_base_dir()
LOCAL_DB_PATH = _get_local_db_path()

APP_VERSION = "3.5.0"

# Remote Railway PostgreSQL — used ONLY for background sync, never for page loads
REMOTE_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:QBvmWZgCvlBsNsqTNmjVmrKJidsHSYQH@shinkansen.proxy.rlwy.net:24887/railway"
)
if REMOTE_DATABASE_URL.startswith("postgres://"):
    REMOTE_DATABASE_URL = REMOTE_DATABASE_URL.replace("postgres://", "postgresql://", 1)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "nodex-panel-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{LOCAL_DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
