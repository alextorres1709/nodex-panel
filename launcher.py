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


def _patch_media_permissions():
    """
    Monkey-patch pywebview's Cocoa BrowserDelegate to auto-grant
    camera/mic permissions so Jitsi doesn't ask every time.
    """
    try:
        from webview.platforms.cocoa import BrowserView
        import objc

        # WKPermissionDecision.grant = 1
        WK_PERMISSION_GRANT = 1

        def _media_permission_handler(
            self, webview, origin, frame, media_type, decisionHandler
        ):
            """Auto-grant camera and microphone permissions."""
            decisionHandler(WK_PERMISSION_GRANT)

        # Register as an Objective-C method with the correct signature
        # Signature: void (id, SEL, WKWebView, WKSecurityOrigin, WKFrameInfo, WKMediaCaptureType, block)
        sel_name = (
            "webView:requestMediaCapturePermissionForOrigin:"
            "initiatedByFrame:type:decisionHandler:"
        )
        _media_permission_handler = objc.selector(
            _media_permission_handler,
            selector=sel_name.encode(),
            signature=b"v@:@@@q@?",
        )

        # Add the method to BrowserDelegate
        BrowserDelegate = BrowserView.BrowserDelegate
        import objc as _objc
        _objc.classAddMethod(
            BrowserDelegate,
            sel_name.encode(),
            _media_permission_handler,
        )

    except Exception as e:
        import logging
        logging.getLogger("launcher").warning(f"Could not patch media permissions: {e}")


def main():
    if getattr(sys, "frozen", False):
        sys.path.insert(0, sys._MEIPASS)

    from app import create_app
    import webview

    # Patch before creating any windows
    _patch_media_permissions()

    port = find_free_port()
    flask_app = create_app()

    # Add restart endpoint for auto-updater
    @flask_app.route("/__restart__")
    def _restart():
        threading.Thread(target=_delayed_restart, daemon=True).start()
        return "Restarting...", 200

    def _delayed_restart():
        time.sleep(0.5)
        from services.updater import _restart_app
        _restart_app()

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
        """Wait for Flask to be ready, navigate, then check for updates."""
        import urllib.request
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=1)
                win.load_url(url)
                # Start auto-updater after successful navigation
                from services.updater import check_and_update
                threading.Thread(
                    target=check_and_update, args=(win,), daemon=True
                ).start()
                return
            except Exception:
                time.sleep(0.1)
        win.load_url(url)

    threading.Thread(target=_wait_and_navigate, args=(window,), daemon=True).start()

    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
