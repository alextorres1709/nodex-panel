"""
Auto-updater: checks GitHub Releases for new versions, downloads and
replaces the app bundle, then offers to restart.
"""
import os
import sys
import json
import shutil
import logging
import subprocess
import tempfile
import urllib.request
import threading

log = logging.getLogger("updater")

# Railway server URL — the /api/version endpoint lives here
SERVER_URL = os.getenv(
    "NODEX_SERVER_URL",
    "https://nodex-panel-production.up.railway.app"
)

APP_BUNDLE_PATH = "/Applications/NodexAI Panel.app"


def _get_app_path():
    """Get the path to the running .app bundle."""
    if getattr(sys, "frozen", False):
        # Inside PyInstaller bundle: …/NodexAI Panel.app/Contents/MacOS/…
        path = os.path.dirname(sys.executable)
        # Walk up to find the .app directory
        while path and not path.endswith(".app"):
            path = os.path.dirname(path)
        if path.endswith(".app"):
            return path
    return APP_BUNDLE_PATH


def check_and_update(window):
    """Background thread: check for updates, download, install, prompt restart."""
    try:
        import time
        time.sleep(8)  # Let the app fully load first

        from config import APP_VERSION

        # 1. Check version
        log.info(f"Checking for updates (current: {APP_VERSION})...")
        req = urllib.request.Request(f"{SERVER_URL}/api/version", method="GET")
        req.add_header("User-Agent", "NodexAI-Panel")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            log.info(f"Update check failed (offline?): {e}")
            return

        remote_version = data.get("version", "")
        download_url = data.get("download_url", "")

        if not remote_version or not download_url:
            return

        if remote_version == APP_VERSION:
            log.info("Already up to date")
            return

        # Compare versions (simple: newer = different and remote > local)
        if not _is_newer(remote_version, APP_VERSION):
            return

        log.info(f"New version available: {remote_version}")

        # 2. Show "downloading" banner
        _show_banner(window, f"Descargando actualización v{remote_version}...", show_restart=False)

        # 3. Download DMG
        tmp_dir = tempfile.mkdtemp(prefix="nodex_update_")
        dmg_path = os.path.join(tmp_dir, "update.dmg")

        log.info(f"Downloading {download_url}...")
        urllib.request.urlretrieve(download_url, dmg_path)
        log.info(f"Downloaded to {dmg_path}")

        # 4. Mount DMG
        mount_point = os.path.join(tmp_dir, "mount")
        os.makedirs(mount_point, exist_ok=True)

        result = subprocess.run(
            ["hdiutil", "attach", dmg_path, "-mountpoint", mount_point, "-nobrowse", "-quiet"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            log.error(f"Failed to mount DMG: {result.stderr}")
            _show_banner(window, "Error al montar la actualización", show_restart=False)
            return

        # 5. Find .app inside mounted DMG
        app_name = None
        for item in os.listdir(mount_point):
            if item.endswith(".app"):
                app_name = item
                break

        if not app_name:
            log.error("No .app found in DMG")
            subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)
            return

        source_app = os.path.join(mount_point, app_name)
        target_app = _get_app_path()

        # 6. Replace: delete old, copy new
        log.info(f"Installing: {source_app} → {target_app}")

        # Use rsync to overwrite in-place (safe even while running)
        result = subprocess.run(
            ["rsync", "-a", "--delete", source_app + "/", target_app + "/"],
            capture_output=True, text=True
        )

        # 7. Unmount and clean up
        subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if result.returncode != 0:
            log.error(f"rsync failed: {result.stderr}")
            _show_banner(window, "Error al instalar la actualización", show_restart=False)
            return

        log.info(f"Update to v{remote_version} installed successfully")

        # 8. Show restart banner
        _show_banner(
            window,
            f"v{remote_version} instalada ✓",
            show_restart=True
        )

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


def _show_banner(window, message, show_restart=False):
    """Show a banner at the top of the app via JS injection."""
    restart_btn = ""
    if show_restart:
        restart_btn = (
            '<button onclick="fetch(\\'/__restart__\\')" '
            'style="background:white;color:#7c3aed;border:none;padding:4px 14px;'
            'border-radius:6px;font-weight:700;cursor:pointer;font-size:12px;'
            'margin-left:8px">Reiniciar</button>'
        )

    js = f"""
    (function() {{
        var old = document.getElementById('update-banner');
        if (old) old.remove();
        var b = document.createElement('div');
        b.id = 'update-banner';
        b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#7c3aed;color:white;padding:10px 20px;display:flex;align-items:center;justify-content:center;gap:12px;font-family:-apple-system,sans-serif;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.3);';
        b.innerHTML = '{message}{restart_btn}<button onclick="this.parentNode.remove()" style="background:none;border:none;color:rgba(255,255,255,.7);cursor:pointer;font-size:16px;margin-left:8px">&times;</button>';
        document.body.prepend(b);
    }})();
    """
    try:
        window.evaluate_js(js)
    except Exception:
        pass


def _restart_app():
    """Relaunch the app by exec-ing the current executable."""
    app_path = _get_app_path()
    if app_path and os.path.isdir(app_path):
        os.execv("/usr/bin/open", ["open", "-n", app_path])
    # Fallback: just quit and let user reopen
    sys.exit(0)
