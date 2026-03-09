import os
from cryptography.fernet import Fernet

_key = os.getenv("ENCRYPTION_KEY")
if not _key:
    _key = Fernet.generate_key().decode()

_fernet = Fernet(_key.encode() if isinstance(_key, str) else _key)


def encrypt(text):
    """Encrypt a string. Returns empty string if input is empty."""
    if not text:
        return ""
    return _fernet.encrypt(text.encode()).decode()


def decrypt(text):
    """Decrypt a string. Returns empty string if input is empty or decryption fails."""
    if not text:
        return ""
    try:
        return _fernet.decrypt(text.encode()).decode()
    except Exception:
        # If decryption fails (e.g. old unencrypted data), return as-is
        return text