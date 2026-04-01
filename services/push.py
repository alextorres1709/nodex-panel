"""
Firebase Cloud Messaging (FCM) push notification sender.
Sends native push notifications to Android (and iOS) devices.
"""
import base64
import json
import logging
import threading

log = logging.getLogger("push")

_fcm_ready = False


def init_fcm():
    """Initialize Firebase Admin SDK from base64-encoded credentials."""
    global _fcm_ready
    from config import FIREBASE_CREDENTIALS_B64

    if not FIREBASE_CREDENTIALS_B64:
        log.info("FCM disabled — FIREBASE_CREDENTIALS_B64 not set")
        return

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_json = base64.b64decode(FIREBASE_CREDENTIALS_B64).decode("utf-8")
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        _fcm_ready = True
        log.info("FCM initialized successfully")
    except Exception as e:
        log.warning(f"FCM init failed: {e}")


def send_push(user_id, title, body="", link="/dashboard"):
    """Send push notification to all registered devices for a user.
    Runs in a background thread to avoid blocking the request.
    """
    if not _fcm_ready:
        return

    threading.Thread(
        target=_send_push_sync,
        args=(user_id, title, body, link),
        daemon=True,
    ).start()


def _send_push_sync(user_id, title, body, link):
    """Synchronous push sender (runs in background thread)."""
    try:
        from firebase_admin import messaging
        from models import db, PushToken
        from flask import current_app

        # Need app context for DB access in background thread
        from app import app as flask_app
        with flask_app.app_context():
            tokens = PushToken.query.filter_by(user_id=user_id).all()
            if not tokens:
                return

            for pt in tokens:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data={
                            "link": link,
                            "click_action": link,
                        },
                        token=pt.token,
                        android=messaging.AndroidConfig(
                            priority="high",
                            notification=messaging.AndroidNotification(
                                icon="ic_notification",
                                color="#4ccd5c",
                                channel_id="nodexai_notifications",
                            ),
                        ),
                    )
                    messaging.send(message)
                except messaging.UnregisteredError:
                    log.info(f"Removing stale FCM token for user {user_id}")
                    db.session.delete(pt)
                    db.session.commit()
                except Exception as e:
                    log.warning(f"FCM send failed for user {user_id}: {e}")

    except Exception as e:
        log.warning(f"FCM push error: {e}")
