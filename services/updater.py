"""
Auto-updater: checks GitHub Releases for new versions, downloads and
replaces the app bundle, then offers to restart.
Uses the public GitHub API — no Railway dependency needed.
"""
import os
import sys
import json
import logging
import urllib.request

log = logging.getLogger("updater")

GITHUB_REPO = "alextorres1709/nodex-panel"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

APP_BUNDLE_PATH = "/Applications/NodexAI Panel.app"

# Latest GitHub release info — always stored so clients can compare their own version
# {"version": "x.x.x", "url": "..."} or None if not yet checked
latest_release = None

# Legacy alias kept for any code that still imports update_available
update_available = None

# Installation progress tracking
install_status = {"state": "idle", "error": None}
# states: "idle", "downloading", "mounting", "installing", "done", "error"


def _get_app_path():
    """Get the path to the running .app bundle."""
    if getattr(sys, "frozen", False):
        path = os.path.dirname(sys.executable)
        while path and not path.endswith(".app"):
            path = os.path.dirname(path)
        if path.endswith(".app"):
            return path
    return APP_BUNDLE_PATH


def check_and_update(window):
    """Background thread: fetch latest GitHub release and store it.
    Each client sends its own version to /api/update/check for comparison.
    """
    try:
        import time
        time.sleep(5)  # Wait for pywebview to load

        from config import APP_VERSION

        # 1. Check latest release on GitHub
        log.info(f"Checking GitHub for latest release (server is {APP_VERSION})...")
        req = urllib.request.Request(GITHUB_API)
        req.add_header("User-Agent", "NodexAI-Panel")
        req.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                release = json.loads(resp.read().decode())
        except Exception as e:
            log.info(f"Update check failed (offline?): {e}")
            return

        # Extract version from tag (e.g. "v2.1.0" -> "2.1.0")
        tag = release.get("tag_name", "")
        remote_version = tag.lstrip("v")

        if not remote_version:
            return

        release_url = release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")

        # Always store the latest GitHub release so ANY client can compare
        # its own installed version against it (not the server's version).
        global latest_release, update_available
        latest_release = {"version": remote_version, "url": release_url}
        log.info(f"Latest GitHub release stored: {remote_version}")

        # Legacy: also set update_available if newer than the SERVER version
        if _is_newer(remote_version, APP_VERSION):
            update_available = latest_release
            log.info(f"Server is also behind — update_available set.")

    except Exception as e:
        log.warning(f"Update error: {e}")


def _is_newer(remote, local):
    """Compare version strings like '1.3.1' > '1.3.0'."""
    try:
        r = [int(x) for x in remote.split(".")]
        l = [int(x) for x in local.split(".")]
        return r > l
    except (ValueError, AttributeError):
        return remote != local


def _restart_app():
    """Relaunch the app."""
    app_path = _get_app_path()
    if app_path and os.path.isdir(app_path):
        os.execv("/usr/bin/open", ["open", "-n", app_path])
    sys.exit(0)
