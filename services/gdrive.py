"""
Google Drive file storage via service account.
Upload, download, and delete files from a shared Google Drive folder.
Falls back gracefully (returns None) when credentials are not configured.
"""
import base64
import io
import json
import logging

log = logging.getLogger("gdrive")

_drive_service = None
_folder_id = None


def init_gdrive():
    """Initialize Google Drive API client from base64-encoded service account credentials."""
    global _drive_service, _folder_id
    from config import GOOGLE_DRIVE_CREDENTIALS_B64, GOOGLE_DRIVE_FOLDER_ID

    if not GOOGLE_DRIVE_CREDENTIALS_B64:
        log.info("Google Drive disabled — GOOGLE_DRIVE_CREDENTIALS_B64 not set")
        return

    if not GOOGLE_DRIVE_FOLDER_ID:
        log.warning("Google Drive disabled — GOOGLE_DRIVE_FOLDER_ID not set")
        return

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        cred_json = base64.b64decode(GOOGLE_DRIVE_CREDENTIALS_B64).decode("utf-8")
        cred_dict = json.loads(cred_json)
        credentials = service_account.Credentials.from_service_account_info(
            cred_dict,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        _drive_service = build("drive", "v3", credentials=credentials)
        _folder_id = GOOGLE_DRIVE_FOLDER_ID

        log.info("Google Drive initialized successfully")
    except Exception as e:
        log.warning(f"Google Drive init failed: {e}")


def is_available():
    """Check if Google Drive is configured and ready."""
    return _drive_service is not None and _folder_id is not None


def upload_file(file_stream, filename, mime_type):
    """Upload a file to the shared Google Drive folder.

    Returns the Google Drive file ID (str) on success, or None on failure.
    """
    if not is_available():
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        file_metadata = {
            "name": filename,
            "parents": [_folder_id],
        }

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
        ).execute()

        drive_file_id = result.get("id")
        log.info(f"Uploaded to Drive: {filename} -> {drive_file_id}")
        return drive_file_id

    except Exception as e:
        log.error(f"Drive upload failed for {filename}: {e}")
        return None


def download_file(drive_file_id):
    """Download a file from Google Drive into memory.

    Returns a BytesIO object with the file contents, or None on failure.
    """
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
        log.info(f"Downloaded from Drive: {drive_file_id}")
        return buffer

    except Exception as e:
        log.error(f"Drive download failed for {drive_file_id}: {e}")
        return None


def delete_file(drive_file_id):
    """Delete a file from Google Drive.

    Returns True on success, False on failure.
    """
    if not is_available():
        return False

    try:
        _drive_service.files().delete(fileId=drive_file_id).execute()
        log.info(f"Deleted from Drive: {drive_file_id}")
        return True

    except Exception as e:
        log.error(f"Drive delete failed for {drive_file_id}: {e}")
        return False
