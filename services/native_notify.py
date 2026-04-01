"""
Native macOS notifications via PyObjC.
Uses NSUserNotificationCenter so notifications are attributed to the app
(not Script Editor like osascript) and appear in System Settings > Notifications.
"""
import sys


def send_native_notification(title="NodexAI Panel", body=""):
    """Send a native macOS notification. No-op on other platforms."""
    if sys.platform != "darwin":
        return False
    try:
        from Foundation import (
            NSUserNotification,
            NSUserNotificationCenter,
        )

        n = NSUserNotification.alloc().init()
        n.setTitle_(title)
        if body:
            n.setInformativeText_(body)
        n.setSoundName_("default")
        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        center.deliverNotification_(n)
        return True
    except Exception:
        return False
