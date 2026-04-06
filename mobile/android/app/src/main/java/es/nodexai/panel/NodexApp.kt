package es.nodexai.panel

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

/**
 * Application subclass that runs once when the app process is created,
 * before any Activity or Service. We create the FCM notification channel
 * here so background-delivered notifications always have a valid channel
 * to render in, even if the user has never opened MainActivity yet.
 */
class NodexApp : Application() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NodexFirebaseService.CHANNEL_ID,
                NodexFirebaseService.CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificaciones de NodexAI Panel"
                enableVibration(true)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
}
