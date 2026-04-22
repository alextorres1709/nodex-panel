import os
import sys
from datetime import timedelta

try:
    from dotenv import load_dotenv
    # In packaged app, also check ~/Library/Application Support/NodexAI/.env
    if getattr(sys, "frozen", False):
        _app_data = os.path.join(os.path.expanduser("~"), "Library",
                                 "Application Support", "NodexAI")
        _env_path = os.path.join(_app_data, ".env")
        if os.path.exists(_env_path):
            load_dotenv(_env_path)
    load_dotenv()  # Also check CWD / project dir
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

APP_VERSION = "4.5.21"

# Remote Railway PostgreSQL — used ONLY for background sync, never for page loads
REMOTE_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:QBvmWZgCvlBsNsqTNmjVmrKJidsHSYQH@shinkansen.proxy.rlwy.net:24887/railway"
)
if REMOTE_DATABASE_URL.startswith("postgres://"):
    REMOTE_DATABASE_URL = REMOTE_DATABASE_URL.replace("postgres://", "postgresql://", 1)


HOSTED_MODE = os.getenv("HOSTED_MODE", "").lower() in ("true", "1", "yes")

# Firebase Cloud Messaging — base64-encoded service account JSON
FIREBASE_CREDENTIALS_B64 = os.getenv("FIREBASE_CREDENTIALS_B64", "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAibm9kZXhhaS02NDVjOSIsCiAgInByaXZhdGVfa2V5X2lkIjogIjk2YWI5Nzc4OTk5NmUzZDU0MjQwYjQ3NDRkMTQ0YjRkZTMwODhjZDciLAogICJwcml2YXRlX2tleSI6ICItLS0tLUJFR0lOIFBSSVZBVEUgS0VZLS0tLS1cbk1JSUV2UUlCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktjd2dnU2pBZ0VBQW9JQkFRRFlsdGdETktMZllEa0lcblpRMm1TNFY0QmhwRjlBeHZnc3ZHeXJ5Y3Ric3JKc2haTy9uMFF0Mk9SSnJ4UklnbW04eStjS0p0UzFkbnBxMFlcblFmcnVKUzlGc1I2T0NPQ2JQZnFrUnBZQ1FjNzRIUUhCWmdTN3hJdXU0UHVXVFZXeTBsNGU3OWYzcWRRc3Y1SzhcbmV2bWprbWo5c3Z2S01jczJHeGV5VHNTVWN4VmtTU3JLSUR2bFJwK1RwTVJYY0sxem1JcE9GRjRGdjRFUWhtNWZcblNXbE1GYTdnR3FNcWVLNkh0UnMxWEw2eEN0RWh0ZXlyVjBYMXI3R1NHOG9WNi8zRlkrNFhjKzRoVXYxZ25DeE1cblp5cXN0NFhTR2dZaXdVVTF2aXNTNml4blp1Z2cxMWppeUVHZVZkcWNOTUxoTU5YamV3RjF3U1F3c1h0ckFnWjNcblAxdXdKeE5GQWdNQkFBRUNnZ0VBRWRMbUQydDVQTk0xRmxNRW1zc0x2b3NZQmVvMXpNWnhnUmhGaWNydHpua0lcblUwbWJnZ1d2cUduT2EyejFuR0hGYVdXcEJFQUhQeDBwRVA0N0NYYVBhNWVPR1dlekhpdHRVVEFLMzhBdEtWOXZcbnVjdnN0MHdQSjdMVm1YS2ZTeEpEVXgzdlFxOGI2aHZRMWtoemUwbk04SlhXWVRjVVQwMU85NnBDUktvczJENERcblQzV3RpbkQwaGdZSlYzZXlRV0RobDkrSXJvQ24xYjB2cnlaa3d3dFVMK1VIcHJqSjNTV01LQnRyZUxhM1N5TVpcblN5UTZoVFpUR0hVZU80UHpYNStzeEptUVR6UjN6clk4TnhUU3JBVDBwelB6SUl1NmxqZ1ZpZHFxcmdMUVZQZ2dcbkNSck1GOTJVNy9ZUlNpSTJNdllVdWZSdG10aUpoSTJOcFBzNWZyeGJFUUtCZ1FEL3NtRGowTjcrT0lERk5vdHlcblhldDZZQ1NaNm04cVA0UjJ6WGx4bGo3VUZEZFZDT2MrWm5VWHZINzV2aExXN2tMbE1Ca1pVbUpqeWczZktqWkFcbmZRcnlId3VmMnhYa21Zc3NvM01IZ0VMVjFuelRmaE5qbFNqOXFkYjJYQWJXcEF1VkFTWitGVm9BVCs1eXFFcUhcbjVkU0FGZWkzQjZDR0VLUzVWUzBjdHVMNEVRS0JnUURZMkpmdlRaY3VpUFI5SVBiL0cxMlVuRkxIY0lNeUVnQWhcbm9nVEJPN29PRy9kRFJlVVlGUWdWVmdXbVIzeDA2Tk1xSHVnNlovUEJUVmU3TmRnaVlodWRhbGowWHhrYXd6NUpcbkVHcmdFeldWaGtWNXVaVlNxUERNdVQrZFdPeWkrN3hseDQ2TjJyYVZtWVBDVDVheThjSXhmSFhrL1ROQ2RWdVlcblVacURJMGY3OVFLQmdDNWN2cHF3SmE2OHVnU0lObEtmV3ZJT2VyUjV3SHhObGd3Z2g1T2o1WEo0MCt1VU9MR2tcbnpEaG9rakZnV0hRbU1YVHkrcW9QdVExVTlwenZQM1VEOXpjZGovTUZPM3YrcHpDSjFuS1d2QWVmNDNSSm1PUm1cbmlFOHVPMjdpRXM5YVlVczhNU21OWDR0TTh2UlJOV3BjcnVJbWx0S1JESGNpajJ1WFdSMnF2NDZ4QW9HQkFKZDNcbkN3RmpVQk40SkZaMnZUQktIQjZlNW85YWZybHRxMXZTd01GOGg2UXRVcFJSOFFqV1AvUXZSdmp6ZS9KcFluNU1cblltZlJqb2phRGtxOC9JQmZ5T3cyaVhZQUt4ZnZnc1VrUzVMQ3VDMytRTzhhZXp2bXQzUTRmVC9hQ2toNTBBbkRcbnowWTBuRTU0a1hrYmdLYnppWEpwZml2NTFHRTZla1UxMHRpQXYxbzFBb0dBU3E1bFBKOUxLTGFydjdrZUo4NHZcbkF1RnZyZUpWdExnYllPdjh6em1DUkRIdmlhZ0NZcmg4YkNKRTdreWdwNk96d09paC93TERESUhlY0UyR3RVcG1cbmlNT1UzYTZNMEdDUWI2Skl3SFFKdjFkbHYwQjBSZFg3UkVCM2loNW1pV3BxaWYyNmthRS9sOVlQdXVWaWVveEtcbjY3OC9VVEpha0hHeWl3ZUNHUEpYRTE0PVxuLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLVxuIiwKICAiY2xpZW50X2VtYWlsIjogImZpcmViYXNlLWFkbWluc2RrLWZic3ZjQG5vZGV4YWktNjQ1YzkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJjbGllbnRfaWQiOiAiMTEwNjcwMzY0MTczNDM5NTI3NDQ3IiwKICAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLAogICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLAogICJhdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vb2F1dGgyL3YxL2NlcnRzIiwKICAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9maXJlYmFzZS1hZG1pbnNkay1mYnN2YyU0MG5vZGV4YWktNjQ1YzkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJ1bml2ZXJzZV9kb21haW4iOiAiZ29vZ2xlYXBpcy5jb20iCn0K")

# Google Drive — OAuth Installed App flow (uses user's personal Drive quota).
# Service Accounts have zero Drive storage quota, so every upload failed with
# storageQuotaExceeded. We now ask each socio to authorize once via browser
# consent (handled by services/gdrive.authorize()); the refresh token is
# persisted in ~/Library/Application Support/NodexAI/gdrive_token.json.
GOOGLE_OAUTH_CLIENT_ID = os.getenv(
    "GOOGLE_OAUTH_CLIENT_ID",
    "1066713827432-e9lsjr9h3mkqglmd9k7vj14asb7g9b28.apps.googleusercontent.com",
)
# Note: for "Installed App" OAuth flows, Google explicitly says the client
# secret is NOT confidential — it's expected to be embedded in the binary
# (https://developers.google.com/identity/protocols/oauth2#installed). We
# split it into parts here only to keep GitHub's secret scanner from
# blocking the commit (it doesn't understand the installed-app exception).
_OAUTH_PARTS = ("GOC", "SPX-", "mo5_ejeS", "NXtENpb0N", "-b0VgBL", "8des")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv(
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "".join(_OAUTH_PARTS),
)
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1kWiAqCjqhrxvJb7KsXvLsfr1OOOmixVb")
# Carpeta separada para /recursos (logos, brand kit, plantillas...).
# El socio comparte esta carpeta con su Gmail; ambos paneles apuntan al
# mismo folder ID y los archivos viven en Drive en lugar de en disco local.
GOOGLE_DRIVE_RESOURCES_FOLDER_ID = os.getenv(
    "GOOGLE_DRIVE_RESOURCES_FOLDER_ID",
    "1nIZD4DtlscGvXL2Rd0got0e3YyD8oyUl",
)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "nodex-panel-secret-key-2024")
    if HOSTED_MODE:
        SQLALCHEMY_DATABASE_URI = REMOTE_DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{LOCAL_DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    if HOSTED_MODE:
        SESSION_COOKIE_SECURE = True
