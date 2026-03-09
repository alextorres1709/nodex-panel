import os
import sys
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_database_url():
    """Get database URL. Supports PostgreSQL (server) and SQLite (local/DMG)."""
    url = os.getenv("DATABASE_URL")
    if url:
        # Railway/Render use postgres:// but SQLAlchemy requires postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    # Fallback: local SQLite
    if getattr(sys, "frozen", False):
        support = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "NodexAI Panel")
        os.makedirs(support, exist_ok=True)
        return f"sqlite:///{os.path.join(support, 'nodex_panel.db')}"
    return f"sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nodex_panel.db')}"


def _get_base_dir():
    """Return the directory containing templates/static."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_base_dir()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "nodex-panel-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
