"""
NodexAI Panel — macOS Native App
Starts Flask in a background thread and opens a native WebKit window.
"""
import sys
import os
import socket
import threading


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(app, port):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


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
    webview.create_window(
        "NodexAI Panel",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=820,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
