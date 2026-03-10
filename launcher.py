"""
NodexAI Panel — macOS Native App
Starts Flask in a background thread and opens a native WebKit window.
"""
import sys
import os
import socket
import threading
import time


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(app, port):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def check_for_updates(window):
    """Check Railway server for new version and show banner if available."""
    try:
        time.sleep(5)  # Wait for app to load
        from config import APP_VERSION
        import urllib.request
        import json

        # Try the Railway server URL (set via env or default)
        server_url = os.getenv("NODEX_SERVER_URL", "")
        if not server_url:
            return

        req = urllib.request.Request(f"{server_url}/api/version", method="GET")
        req.add_header("User-Agent", "NodexAI-Panel")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        remote_version = data.get("version", "")
        download_url = data.get("download_url", "")

        if remote_version and remote_version != APP_VERSION and download_url:
            js = f"""
            (function() {{
                if (document.getElementById('update-banner')) return;
                var b = document.createElement('div');
                b.id = 'update-banner';
                b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;background:#7c3aed;color:white;padding:10px 20px;display:flex;align-items:center;justify-content:center;gap:12px;font-family:Inter,sans-serif;font-size:13px;';
                b.innerHTML = 'Nueva version {remote_version} disponible <a href="{download_url}" target="_blank" style="color:white;font-weight:700;text-decoration:underline;">Descargar</a> <button onclick="this.parentNode.remove()" style="background:none;border:none;color:white;cursor:pointer;font-size:16px;margin-left:8px;">&times;</button>';
                document.body.prepend(b);
            }})();
            """
            window.evaluate_js(js)
    except Exception:
        pass  # Silent fail — don't block the app


def main():
    if getattr(sys, "frozen", False):
        sys.path.insert(0, sys._MEIPASS)

    from app import create_app
    import webview

    port = find_free_port()
    flask_app = create_app()

    # Run Flask in a daemon thread
    server_thread = threading.Thread(
        target=start_server, args=(flask_app, port), daemon=True
    )
    server_thread.start()

    # Create native window pointing to the Flask server
    window = webview.create_window(
        "NodexAI Panel",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=820,
        min_size=(900, 600),
    )

    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
