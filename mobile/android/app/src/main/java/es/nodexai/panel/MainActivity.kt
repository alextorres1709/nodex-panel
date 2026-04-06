package es.nodexai.panel

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.button.MaterialButton
import com.google.firebase.messaging.FirebaseMessaging

class MainActivity : AppCompatActivity() {

    companion object {
        const val BASE_URL = "https://web-production-fcc14.up.railway.app"
    }

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var offlineOverlay: LinearLayout
    private var fileUploadCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val data = result.data
        val results = if (result.resultCode == RESULT_OK && data != null) {
            WebChromeClient.FileChooserParams.parseResult(result.resultCode, data)
        } else null
        fileUploadCallback?.onReceiveValue(results)
        fileUploadCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        offlineOverlay = findViewById(R.id.offlineOverlay)
        val retryButton = findViewById<MaterialButton>(R.id.retryButton)

        // SwipeRefreshLayout
        swipeRefresh.setColorSchemeColors(
            resources.getColor(R.color.accent_purple, theme),
            resources.getColor(R.color.accent_blue, theme)
        )
        swipeRefresh.setOnRefreshListener {
            webView.reload()
        }

        // Retry button
        retryButton.setOnClickListener {
            offlineOverlay.visibility = View.GONE
            webView.reload()
        }

        // Configure WebView
        setupWebView()

        // Enable cookies for session persistence
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        // Network state monitoring
        registerNetworkCallback()

        // Request notification permission (Android 13+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED
            ) {
                requestPermissions(
                    arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1001
                )
            }
        }

        // Create notification channel early so background FCM notifications work on Android 8+
        createNotificationChannel()

        // Load the app (or navigate to notification deep link)
        val notifLink = intent?.getStringExtra("link")
        webView.loadUrl(if (notifLink != null) "$BASE_URL$notifLink" else BASE_URL)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            setSupportZoom(false)
            useWideViewPort = true
            loadWithOverviewMode = false
            allowFileAccess = true
            mediaPlaybackRequiresUserGesture = false
            setSupportMultipleWindows(false)
            userAgentString = userAgentString.replace("; wv", "")  // Remove WebView marker
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                swipeRefresh.isRefreshing = true
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                offlineOverlay.visibility = View.GONE

                // Inject viewport meta if missing and mark as Android
                view?.evaluateJavascript("""
                    (function() {
                        if (!document.querySelector('meta[name="viewport"]')) {
                            var meta = document.createElement('meta');
                            meta.name = 'viewport';
                            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
                            document.head.appendChild(meta);
                        }
                        document.documentElement.classList.add('android-webview');
                    })();
                """.trimIndent(), null)

                // Register FCM token & save session cookie
                if (url?.startsWith(BASE_URL) == true) {
                    registerFcmToken(view)
                    saveSessionCookie()
                }
            }

            override fun onReceivedError(
                view: WebView?, request: WebResourceRequest?, error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    offlineOverlay.visibility = View.VISIBLE
                }
            }

            override fun shouldOverrideUrlLoading(
                view: WebView?, request: WebResourceRequest?
            ): Boolean {
                val url = request?.url?.toString() ?: return false
                return if (url.startsWith(BASE_URL) || url.startsWith("https://nodex")) {
                    false
                } else {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    true
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?
            ): Boolean {
                fileUploadCallback?.onReceiveValue(null)
                fileUploadCallback = callback
                val intent = params?.createIntent() ?: return false
                fileChooserLauncher.launch(intent)
                return true
            }
        }
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

    private fun registerNetworkCallback() {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()

        cm.registerNetworkCallback(request, object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                runOnUiThread {
                    if (offlineOverlay.visibility == View.VISIBLE) {
                        offlineOverlay.visibility = View.GONE
                        webView.reload()
                    }
                }
            }

            override fun onLost(network: Network) {
                runOnUiThread {
                    offlineOverlay.visibility = View.VISIBLE
                }
            }
        })
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.getStringExtra("link")?.let { link ->
            webView.loadUrl("$BASE_URL$link")
        }
    }

    private fun registerFcmToken(webView: WebView?) {
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                Log.d("NodexFCM", "FCM token: $token")
                getSharedPreferences("nodexai", MODE_PRIVATE).edit()
                    .putString("fcm_token", token).apply()
                webView?.evaluateJavascript("""
                    fetch('/api/push/register', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({token: '$token', platform: 'android'})
                    }).then(function(r){ console.log('FCM register: ' + r.status); })
                      .catch(function(e){ console.error('FCM register err: ' + e); });
                """.trimIndent(), null)
            }
            .addOnFailureListener { e ->
                Log.e("NodexFCM", "Token error: ${e.message}")
            }
    }

    private fun saveSessionCookie() {
        val cookies = CookieManager.getInstance().getCookie(BASE_URL) ?: return
        getSharedPreferences("nodexai", MODE_PRIVATE).edit()
            .putString("session_cookie", cookies).apply()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        webView.onPause()
        super.onPause()
    }
}
