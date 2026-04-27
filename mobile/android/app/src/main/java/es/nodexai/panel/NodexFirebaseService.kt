package es.nodexai.panel

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.net.HttpURLConnection
import java.net.URL

class NodexFirebaseService : FirebaseMessagingService() {

    companion object {
        const val TAG = "NodexFCM"
        const val CHANNEL_ID = "nodexai_notifications"
        const val CHANNEL_NAME = "NodexAI"
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "New FCM token: $token")
        // Always save the latest token so MainActivity can register it on next load
        getSharedPreferences("nodexai", MODE_PRIVATE).edit()
            .putString("pending_fcm_token", token).apply()
        registerTokenWithBackend(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        Log.d(TAG, "Message received: ${message.data}")

        val title = message.notification?.title ?: message.data["title"] ?: "NodexAI"
        val body = message.notification?.body ?: message.data["body"] ?: ""
        val link = message.data["link"] ?: "/dashboard"

        showNotification(title, body, link)
    }

    private fun showNotification(title: String, body: String, link: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager

        // Create notification channel (required for Android 8+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificaciones de NodexAI Panel"
                enableVibration(true)
            }
            manager.createNotificationChannel(channel)
        }

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("link", link)
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setVibrate(longArrayOf(0, 300, 100, 300))
            .build()

        manager.notify(System.currentTimeMillis().toInt(), notification)
    }

    private fun registerTokenWithBackend(token: String) {
        // Use session cookie saved by MainActivity
        val prefs = getSharedPreferences("nodexai", MODE_PRIVATE)
        val cookie = prefs.getString("session_cookie", null) ?: return

        Thread {
            try {
                val url = URL("${MainActivity.BASE_URL}/api/push/register")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Cookie", cookie)
                conn.doOutput = true
                conn.outputStream.use { os ->
                    os.write("""{"token":"$token","platform":"android"}""".toByteArray())
                }
                val code = conn.responseCode
                Log.d(TAG, "Token registered: HTTP $code")
                conn.disconnect()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to register token: ${e.message}")
            }
        }.start()
    }
}
