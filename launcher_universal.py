"""
NodexAI Panel — Cross-Platform Desktop App
Starts Flask in a background thread and opens a native WebView window.
Works on macOS, Windows, and Linux. macOS-specific enhancements applied when available.
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


# ── macOS-specific enhancements (safe no-ops on other platforms) ──

def _patch_media_permissions():
    """Auto-grant camera/mic permissions for Jitsi on macOS."""
    if sys.platform != "darwin":
        return
    import platform
    try:
        major_ver = int(platform.mac_ver()[0].split(".")[0])
        if major_ver >= 26:
            return
    except Exception:
        pass

    try:
        from webview.platforms.cocoa import BrowserView
        import objc

        WK_PERMISSION_GRANT = 1

        def _media_permission_handler(
            self, webview, origin, frame, media_type, decisionHandler
        ):
            try:
                decisionHandler(WK_PERMISSION_GRANT)
            except Exception:
                pass

        sel_name = (
            "webView:requestMediaCapturePermissionForOrigin:"
            "initiatedByFrame:type:decisionHandler:"
        )
        _media_permission_handler = objc.selector(
            _media_permission_handler,
            selector=sel_name.encode(),
            signature=b"v@:@@@q@?",
        )

        BrowserDelegate = BrowserView.BrowserDelegate
        objc.classAddMethod(
            BrowserDelegate,
            sel_name.encode(),
            _media_permission_handler,
        )
    except Exception:
        pass


def _keep_process_alive():
    """Prevent macOS from suspending the process (App Nap) and keep
    it visible to external process monitors like Discord."""
    if sys.platform != "darwin":
        return

    # Disable App Nap
    try:
        from Foundation import NSProcessInfo
        activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            0x00FFFFFF,
            "NodexAI Panel must remain active"
        )
        _keep_process_alive._activity = activity
    except Exception:
        pass

    # Ensure foreground app
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyRegular
        )
    except Exception:
        pass

    # Background heartbeat
    def _heartbeat():
        import gc
        while True:
            time.sleep(10)
            gc.collect(0)

    threading.Thread(target=_heartbeat, daemon=True).start()


def _patch_easy_drag():
    """Patch pywebview cocoa backend so easy_drag works WITHOUT frameless.
    Drag is allowed only when clicking in the top 70px of the window
    (covers the transparent titlebar + header bar)."""
    if sys.platform != "darwin":
        return
    try:
        from webview.platforms.cocoa import BrowserView
        import AppKit
        import WebKit

        DRAG_HEIGHT = 70  # px from top of window that acts as drag zone

        def _mouseDown(self, event):
            i = BrowserView.get_instance('webview', self)
            self._nodex_is_dragging = False
            if i.easy_drag:
                loc = event.locationInWindow()
                view_height = self.frame().size.height
                y_from_top = view_height - loc.y
                if y_from_top <= DRAG_HEIGHT:
                    self._nodex_is_dragging = True
                    window = self.window()
                    windowFrame = window.frame()
                    if windowFrame is not None:
                        self.initialLocation = window.convertBaseToScreen_(event.locationInWindow())
                        self.initialLocation.x -= windowFrame.origin.x
                        self.initialLocation.y -= windowFrame.origin.y
            WebKit.WKWebView.mouseDown_(self, event)

        def _mouseDragged(self, event):
            i = BrowserView.get_instance('webview', self)
            if i.easy_drag and getattr(self, '_nodex_is_dragging', False):
                window = self.window()
                screenFrame = i.screen
                windowFrame = window.frame()
                if screenFrame is not None and windowFrame is not None:
                    currentLocation = window.convertBaseToScreen_(
                        window.mouseLocationOutsideOfEventStream()
                    )
                    newOrigin = AppKit.NSMakePoint(
                        currentLocation.x - self.initialLocation.x,
                        currentLocation.y - self.initialLocation.y,
                    )
                    if (newOrigin.y + windowFrame.size.height) > (
                        screenFrame.origin.y + screenFrame.size.height
                    ):
                        newOrigin.y = screenFrame.origin.y + (
                            screenFrame.size.height + windowFrame.size.height
                        )
                    window.setFrameOrigin_(newOrigin)
                return
            WebKit.WKWebView.mouseDragged_(self, event)

        BrowserView.WebKitHost.mouseDown_ = _mouseDown
        BrowserView.WebKitHost.mouseDragged_ = _mouseDragged
    except Exception:
        pass


_fullscreen_observers = []  # prevent GC of NSNotification observers


def _configure_native_window_macos():
    """Apply macOS-specific native window styling (transparent titlebar, fullscreen)."""
    if sys.platform != "darwin":
        return

    def _apply():
        try:
            from AppKit import NSApp, NSColor
            windows = NSApp.windows()
            if not windows:
                return
            nswindow = windows[0]

            # Hide the native title text and make titlebar transparent
            nswindow.setTitle_("")
            nswindow.setTitleVisibility_(1)  # NSWindowTitleHidden
            nswindow.setTitlebarAppearsTransparent_(True)

            # Extend content behind titlebar (NSFullSizeContentViewWindowMask)
            mask = nswindow.styleMask()
            nswindow.setStyleMask_(mask | (1 << 15))
            nswindow.setMovableByWindowBackground_(False)

            try:
                nswindow.setTitlebarSeparatorStyle_(0)
            except Exception:
                pass

            # Remove any toolbar that pywebview may have added
            if nswindow.toolbar():
                nswindow.toolbar().setVisible_(False)
                nswindow.setToolbar_(None)

            # Window background matches dark mode CSS (#050505)
            nswindow.setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    5/255, 5/255, 5/255, 1.0
                )
            )

            # Aggressively hide ALL titlebar background/decoration views,
            # keeping only the traffic-light buttons visible.
            def _nuke_titlebar_bg(view, depth=0):
                cls_name = str(view.className())
                # Keep traffic-light button container and its children
                if "WindowButtonContainer" in cls_name or \
                   "_NSThemeCloseWidget" in cls_name or \
                   "_NSThemeZoomWidget" in cls_name or \
                   "_NSThemeFullScreenButton" in cls_name or \
                   "NSThemeWidget" in cls_name:
                    return
                # Hide visual effects, decorations, separators
                if any(k in cls_name for k in (
                    "NSVisualEffectView", "DecorationView",
                    "SeparatorView", "NSTitlebarAccessory",
                    "ToolbarItemViewer", "NSToolbar",
                )):
                    view.setHidden_(True)
                    try:
                        view.setAlphaValue_(0)
                    except Exception:
                        pass
                    return
                # Clear layer background on containers
                try:
                    view.setWantsLayer_(True)
                    layer = view.layer()
                    if layer:
                        layer.setBackgroundColor_(None)
                except Exception:
                    pass
                # Recurse into children
                try:
                    for child in view.subviews():
                        _nuke_titlebar_bg(child, depth + 1)
                except Exception:
                    pass

            try:
                theme_frame = nswindow.contentView().superview()
                for subview in theme_frame.subviews():
                    cls_name = str(subview.className())
                    if "NSTitlebarContainerView" in cls_name:
                        # Clear the container's own background
                        subview.setWantsLayer_(True)
                        if subview.layer():
                            subview.layer().setBackgroundColor_(None)
                        _nuke_titlebar_bg(subview)
            except Exception:
                pass

            # Force the WKWebView to fill the entire window (behind titlebar)
            content_view = nswindow.contentView()
            if content_view:
                bounds = content_view.bounds()
                for subview in content_view.subviews():
                    subview.setFrame_(bounds)
                    subview.setAutoresizingMask_(18)  # Width + Height sizable

            behavior = nswindow.collectionBehavior()
            behavior |= (1 << 2) | (1 << 7)
            nswindow.setCollectionBehavior_(behavior)

            # Observe fullscreen enter/exit to toggle CSS class
            try:
                from Foundation import NSNotificationCenter, NSOperationQueue

                def _find_wkwebview():
                    try:
                        cv = nswindow.contentView()
                        for sv in cv.subviews():
                            if "WKWebView" in str(sv.className()):
                                return sv
                    except Exception:
                        pass
                    return None

                def _on_enter_fs(notif):
                    wk = _find_wkwebview()
                    if wk:
                        wk.evaluateJavaScript_completionHandler_(
                            "document.documentElement.classList.add('macos-fullscreen');",
                            None,
                        )

                def _on_exit_fs(notif):
                    wk = _find_wkwebview()
                    if wk:
                        wk.evaluateJavaScript_completionHandler_(
                            "document.documentElement.classList.remove('macos-fullscreen');",
                            None,
                        )

                nc = NSNotificationCenter.defaultCenter()
                main_q = NSOperationQueue.mainQueue()
                # Store observers to prevent garbage collection
                _fullscreen_observers.append(
                    nc.addObserverForName_object_queue_usingBlock_(
                        "NSWindowDidEnterFullScreenNotification",
                        nswindow, main_q, _on_enter_fs,
                    )
                )
                _fullscreen_observers.append(
                    nc.addObserverForName_object_queue_usingBlock_(
                        "NSWindowDidExitFullScreenNotification",
                        nswindow, main_q, _on_exit_fs,
                    )
                )
            except Exception:
                pass

            nswindow.display()
        except Exception:
            pass

    def _wait_and_configure():
        try:
            from PyObjCTools.AppHelper import callAfter
            for _ in range(10):
                time.sleep(0.5)
                try:
                    from AppKit import NSApp
                    if NSApp.windows():
                        callAfter(_apply)
                        return
                except Exception:
                    pass
        except Exception:
            pass

    threading.Thread(target=_wait_and_configure, daemon=True).start()


# ── Main entry point ──

LOADING_HTML = """
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;background:#050505;display:flex;justify-content:center;align-items:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;flex-direction:column;overflow:hidden">
    <div style="display:flex;flex-direction:column;align-items:center;gap:18px;transform:translateY(-20px)">
        <img src="data:image/png;base64,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"
             style="width:80px;height:80px;opacity:0;animation:logoIn 0.8s ease-out 0.2s forwards" alt="NodexAI">
        <div style="color:white;font-size:20px;font-weight:700;letter-spacing:2px;opacity:0;animation:fadeIn 0.6s ease-out 0.6s forwards">
            Nodex<span style="color:#3b82f6">AI</span>
        </div>
        <div style="color:#6e7681;font-size:12px;font-weight:400;letter-spacing:0.5px;opacity:0;animation:fadeIn 0.6s ease-out 0.9s forwards">
            Iniciando panel...
        </div>
        <div style="width:220px;height:4px;background:rgba(59,130,246,0.14);border-radius:4px;overflow:hidden;margin-top:4px;opacity:0;animation:fadeIn 0.4s ease-out 1s forwards">
            <div style="width:0%;height:100%;background:linear-gradient(90deg,#3b82f6,#2563eb);border-radius:4px;animation:loadBar 1.8s cubic-bezier(0.4,0,0.2,1) 1.1s infinite;box-shadow:0 0 12px rgba(59,130,246,0.55)"></div>
        </div>
    </div>
    <style>
        @keyframes logoIn { 0%{opacity:0;transform:scale(0.7)} 100%{opacity:1;transform:scale(1)} }
        @keyframes fadeIn { 0%{opacity:0;transform:translateY(6px)} 100%{opacity:1;transform:translateY(0)} }
        @keyframes loadBar { 0%{width:0%;margin-left:0} 40%{width:55%;margin-left:15%} 100%{width:0%;margin-left:100%} }
    </style>
</body>
</html>
"""


class NodexJSBridge:
    """JS API exposed to the WebView via window.pywebview.api.
    Lets the frontend open a native SAVE dialog for downloads and open
    document previews in a new native WebView window."""

    def __init__(self):
        self.port = None  # set after find_free_port()
        self.session_cookie = None  # captured from the main window on demand

    def _fetch_bytes(self, url):
        """Fetch a URL from the local Flask server with the session cookie
        attached, so @login_required routes authorize the request."""
        import urllib.request
        full = f"http://127.0.0.1:{self.port}{url}"
        req = urllib.request.Request(full)
        try:
            import webview as _wv
            if _wv.windows:
                cookies = _wv.windows[0].get_cookies()
                cookie_str = "; ".join(
                    f"{c.key}={c.value.value}" for c in cookies
                    if getattr(c, "key", None) and hasattr(c, "value")
                )
                if cookie_str:
                    req.add_header("Cookie", cookie_str)
        except Exception:
            pass
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def save_document(self, url, filename):
        """Open a native SAVE dialog and write the document bytes there."""
        try:
            import webview as _wv
            win = _wv.windows[0] if _wv.windows else None
            if win is None:
                return {"ok": False, "error": "No window"}
            result = win.create_file_dialog(
                _wv.SAVE_DIALOG,
                save_filename=filename or "documento",
            )
            if not result:
                return {"ok": False, "error": "cancelled"}
            # pywebview returns either a string or a list
            path = result if isinstance(result, str) else result[0]
            data = self._fetch_bytes(url)
            with open(path, "wb") as f:
                f.write(data)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def preview_document(self, url, filename):
        """Open a new native WebView window with the document preview."""
        try:
            import webview as _wv
            full = f"http://127.0.0.1:{self.port}{url}"
            _wv.create_window(
                filename or "Vista previa",
                url=full,
                width=1000,
                height=800,
                min_size=(600, 400),
                background_color="#1a1a1a",
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def main():
    if getattr(sys, "frozen", False):
        sys.path.insert(0, sys._MEIPASS)

    import webview

    # Platform-specific setup
    _keep_process_alive()
    _patch_media_permissions()
    _patch_easy_drag()
    _register_login_item()

    port = find_free_port()
    js_bridge = NodexJSBridge()
    js_bridge.port = port

    window = webview.create_window(
        "NodexAI Panel",
        html=LOADING_HTML,
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color='#050505',
        easy_drag=True,
        js_api=js_bridge,
    )

    def _boot_flask_and_navigate(win):
        from app import create_app
        flask_app = create_app()

        @flask_app.route("/__restart__")
        def _restart():
            threading.Thread(target=_delayed_restart, daemon=True).start()
            return "Restarting...", 200

        def _delayed_restart():
            time.sleep(0.5)
            from services.updater import _restart_app
            _restart_app()

        threading.Thread(
            target=start_server, args=(flask_app, port), daemon=True
        ).start()

        import urllib.request
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=1)
                win.load_url(url)
                from services.updater import check_and_update
                threading.Thread(
                    target=check_and_update, args=(win,), daemon=True
                ).start()
                return
            except Exception:
                time.sleep(0.1)
        win.load_url(url)

    _configure_native_window_macos()
    threading.Thread(target=_boot_flask_and_navigate, args=(window,), daemon=True).start()

    webview.start(private_mode=False)


def _register_login_item():
    """Register the app to open at system startup on macOS."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        app_path = "/Applications/NodexAI Panel.app"
        # Check if already registered
        result = subprocess.run(
            ["/usr/bin/osascript", "-e",
             'tell application "System Events" to get the path of every login item'],
            capture_output=True, text=True, timeout=5
        )
        if app_path in (result.stdout or ""):
            return  # Already registered
        subprocess.run(
            ["/usr/bin/osascript", "-e",
             f'tell application "System Events" to make login item at end '
             f'with properties {{path:"{app_path}", hidden:false}}'],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
