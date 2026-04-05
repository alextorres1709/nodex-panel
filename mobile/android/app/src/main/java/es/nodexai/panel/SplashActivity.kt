package es.nodexai.panel

import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton

class SplashActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)

        val offlineBanner = findViewById<LinearLayout>(R.id.offlineBanner)
        val retryBtn = findViewById<MaterialButton>(R.id.retryBtn)

        retryBtn.setOnClickListener { checkAndProceed(offlineBanner) }

        checkAndProceed(offlineBanner)
    }

    private fun checkAndProceed(offlineBanner: LinearLayout) {
        if (isOnline()) {
            offlineBanner.visibility = View.GONE
            Handler(Looper.getMainLooper()).postDelayed({
                startActivity(Intent(this, MainActivity::class.java))
                finish()
            }, 800)
        } else {
            offlineBanner.visibility = View.VISIBLE
        }
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(net) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
