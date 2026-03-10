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

    # Dark loading page shown while Flask boots
    LOADING_HTML = """
    <html>
    <body style="margin:0;background:#0d1117;display:flex;justify-content:center;align-items:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;flex-direction:column;gap:20px">
        <div style="color:white;font-size:22px;font-weight:600;letter-spacing:1px">NodexAI</div>
        <div style="color:#8b949e;font-size:13px">Iniciando panel...</div>
        <div style="width:200px;height:3px;background:#21262d;border-radius:3px;overflow:hidden;margin-top:8px">
            <div style="width:0%;height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);border-radius:3px;animation:load 2s ease-in-out infinite"></div>
        </div>
        <style>
            @keyframes load { 0%{width:0%;margin-left:0} 50%{width:60%;margin-left:20%} 100%{width:0%;margin-left:100%} }
        </style>
    </body>
    </html>
    """

    window = webview.create_window(
        "NodexAI Panel",
        html=LOADING_HTML,
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color='#0d1117',
    )

    def _wait_and_navigate(win):
        """Wait for Flask to be ready then navigate to it."""
        import urllib.request
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):  # up to 6 seconds
            try:
                urllib.request.urlopen(url, timeout=1)
                win.load_url(url)
                return
            except Exception:
                time.sleep(0.1)
        win.load_url(url)  # try anyway

    threading.Thread(target=_wait_and_navigate, args=(window,), daemon=True).start()

    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
