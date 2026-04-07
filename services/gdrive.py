"""
Google Drive file storage via user OAuth (Installed App flow).

Previously this module used a Google Cloud Service Account, but service
accounts have zero personal Drive storage quota, so every upload failed
with `storageQuotaExceeded`. Now we use the Installed App OAuth flow and
store files in the signed-in user's own Drive (e.g. a Google One paid
plan). Each socio authorizes once; the refresh token is persisted in
the app data dir so subsequent launches don't need re-consent.

To share documents between partners, one user creates a folder in their
Drive, shares it with the other user's Gmail (with "Editor" permission),
and both panels point at the same GOOGLE_DRIVE_FOLDER_ID. Each user
authorizes with their own Google account; both can read/write the folder
because the OAuth account has been explicitly granted access.
"""
import io
import logging
import os
import threading

log = logging.getLogger("gdrive")

_drive_service = None
_folder_id = None
_init_lock = threading.Lock()

# Full Drive scope — we need to read/write files in a folder that was
# shared with the user by another account. The narrower `drive.file`
# scope only covers files created by this OAuth client instance.
SCOPES = ["https://www.googleapis.com/auth/drive"]


def _token_path():
    """Return the absolute path where the OAuth refresh token is stored."""
    from config import LOCAL_DB_PATH  # already in ~/Library/Application Support/NodexAI
    return os.path.join(os.path.dirname(LOCAL_DB_PATH), "gdrive_token.json")


def _build_service(creds):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _load_credentials():
    """Load stored OAuth credentials, refreshing if expired. Returns None
    if the user has never authorized, or if the refresh token is dead."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    path = _token_path()
    if not os.path.exists(path):
        return None

    try:
        creds = Credentials.from_authorized_user_file(path, SCOPES)
    except Exception as e:
        log.warning(f"Failed to load Drive token file: {e}")
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception as e:
            log.warning(f"Failed to refresh Drive token: {e}")
            return None

    if not creds or not creds.valid:
        return None
    return creds


def _save_credentials(creds):
    path = _token_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(creds.to_json())


def _client_config():
    """Return the client_config dict InstalledAppFlow expects."""
    from config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
    return {
        "installed": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }


def init_gdrive():
    """Initialize Google Drive from a stored OAuth token (if any).

    Non-fatal if the user has not authorized yet — the upload path will
    gracefully fall back to local storage, and a visible "Conectar con
    Google Drive" button in the Documentos page lets the user kick off
    the consent flow when they want to.
    """
    global _drive_service, _folder_id
    from config import GOOGLE_DRIVE_FOLDER_ID, GOOGLE_OAUTH_CLIENT_ID

    _folder_id = GOOGLE_DRIVE_FOLDER_ID

    if not GOOGLE_OAUTH_CLIENT_ID:
        log.info("Google Drive disabled — GOOGLE_OAUTH_CLIENT_ID not set")
        return

    if not _folder_id:
        log.warning("Google Drive disabled — GOOGLE_DRIVE_FOLDER_ID not set")
        return

    creds = _load_credentials()
    if not creds:
        log.info("Google Drive: no stored token — user needs to authorize via the UI")
        return

    try:
        _drive_service = _build_service(creds)
        log.info("Google Drive initialized (OAuth user account)")
    except Exception as e:
        log.warning(f"Google Drive init failed: {e}")


def is_available():
    """Check if Drive is configured AND the user has authorized."""
    return _drive_service is not None and _folder_id is not None


def needs_authorization():
    """True when OAuth client is configured but user has not authorized yet."""
    from config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_DRIVE_FOLDER_ID
    if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_DRIVE_FOLDER_ID:
        return False
    return _drive_service is None


def authorize():
    """Run the OAuth consent flow. Blocks (~20-60s) until the user
    finishes the browser prompt. Returns (ok: bool, message: str).

    Called from a user-initiated HTTP request (a button click in the
    Documentos page). Opens the user's default browser and spins up a
    temporary localhost webserver to capture the redirect.
    """
    global _drive_service

    from config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
    if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET:
        return False, "OAuth client credentials not configured"

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        return False, f"google-auth-oauthlib not installed: {e}"

    try:
        with _init_lock:
            flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
            # port=0 → OS picks a free port. This matches the "http://localhost"
            # redirect URI Google accepts for installed-app clients without
            # requiring you to register a specific port.
            creds = flow.run_local_server(
                port=0,
                open_browser=True,
                prompt="consent",
                authorization_prompt_message="",
                success_message="NodexAI Panel conectado a Google Drive. Puedes cerrar esta pestaña.",
            )
            _save_credentials(creds)
            _drive_service = _build_service(creds)
            log.info("Google Drive authorized successfully")
        return True, "Google Drive conectado correctamente"
    except Exception as e:
        log.error(f"Drive authorize failed: {e}")
        return False, f"Error al conectar con Google Drive: {e}"


def disconnect():
    """Forget the stored OAuth token (used for the 'Desconectar' button)."""
    global _drive_service
    path = _token_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        log.warning(f"Failed to delete token file: {e}")
    _drive_service = None


def upload_file(file_stream, filename, mime_type):
    """Upload a file into the shared Drive folder.

    Returns the Drive file ID on success, or None on failure (the caller
    is expected to fall back to local storage).
    """
    if not is_available():
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        file_metadata = {"name": filename, "parents": [_folder_id]}

        if hasattr(file_stream, "seek"):
            file_stream.seek(0)

        media = MediaIoBaseUpload(
            file_stream,
            mimetype=mime_type,
            chunksize=5 * 1024 * 1024,
            resumable=True,
        )

        result = _drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()

        drive_file_id = result.get("id")
        log.info(f"Uploaded to Drive: {filename} -> {drive_file_id}")
        return drive_file_id

    except Exception as e:
        log.error(f"Drive upload failed for {filename}: {e}")
        return None


def download_file(drive_file_id):
    """Download a Drive file into memory. Returns BytesIO or None."""
    if not is_available():
        return None

    try:
        from googleapiclient.http import MediaIoBaseDownload

        request = _drive_service.files().get_media(fileId=drive_file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request, chunksize=10 * 1024 * 1024)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        buffer.seek(0)
        return buffer

    except Exception as e:
        log.error(f"Drive download failed for {drive_file_id}: {e}")
        return None


def delete_file(drive_file_id):
    """Delete a file from Drive. Returns True on success."""
    if not is_available():
        return False

    try:
        _drive_service.files().delete(
            fileId=drive_file_id, supportsAllDrives=True
        ).execute()
        return True
    except Exception as e:
        log.error(f"Drive delete failed for {drive_file_id}: {e}")
        return False
