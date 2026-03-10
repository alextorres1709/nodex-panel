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
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    
    # Fallback: Remote Railway PostgreSQL (External TCP)
    # This ensures all DMG installations connect to the same shared database
    return "postgresql://postgres:QBvmWZgCvlBsNsqTNmjVmrKJidsHSYQH@shinkansen.proxy.rlwy.net:24887/railway"


def _get_base_dir():
    """Return the directory containing templates/static."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_base_dir()

APP_VERSION = "1.2.0"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "nodex-panel-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    # Connection pool: keep 10 connections alive, allow bursts to 20
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,      # auto-reconnect stale connections
        "pool_recycle": 300,         # recycle connections every 5 min
        "connect_args": {
            "connect_timeout": 5,    # fail fast on connection issues
        },
    }
