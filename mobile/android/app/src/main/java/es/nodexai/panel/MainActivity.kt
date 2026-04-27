package es.nodexai.panel

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.util.Log
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.button.MaterialButton
import com.google.firebase.messaging.FirebaseMessaging
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    companion object {
        const val BASE_URL = "https://web-production-fcc14.up.railway.app"

        // Bulletproof CSS+JS injection that suppresses every Flask flash
        // message inside the WebView, regardless of server-side User-Agent
        // checks. Hides the elements via CSS first (so they never render)
        // and then strips them from the DOM and overrides DOM mutators so
        // any later-injected toast also gets killed.
        const val HIDE_FLASHES_JS = """
            (function() {
                try {
                    var STYLE_ID = '__nodex_no_flash__';
                    if (!document.getElementById(STYLE_ID)) {
                        var s = document.createElement('style');
                        s.id = STYLE_ID;
                        s.textContent = '.flash-message,[class*="flash-message"]{display:none !important;visibility:hidden !important;opacity:0 !important;height:0 !important;margin:0 !important;padding:0 !important;overflow:hidden !important}';
                        (document.head || document.documentElement).appendChild(s);
                    }
                    function strip() {
                        var els = document.querySelectorAll('.flash-message');
                        for (var i = 0; i < els.length; i++) {
                            try { els[i].parentNode && els[i].parentNode.removeChild(els[i]); } catch(e){}
                        }
                    }
                    strip();
                    if (!window.__nodex_flash_observer__) {
                        try {
                            var obs = new MutationObserver(strip);
                            obs.observe(document.documentElement, {childList: true, subtree: true});
                            window.__nodex_flash_observer__ = obs;
                        } catch(e) {}
                    }
                } catch(e) {}
            })();
        """
    }

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var offlineOverlay: LinearLayout
    private var fileUploadCallback: ValueCallback<Array<Uri>>? = null
    // Only show the pull-to-refresh spinner when the user explicitly pulls,
    // not on every in-app navigation (which makes sections feel sluggish).
    private var isPullRefreshing = false

    // Pending download info captured when the user taps "Descargar" and
    // handed off to the ACTION_CREATE_DOCUMENT picker result.
    private var pendingDownloadUrl: String? = null
    private var pendingDownloadName: String? = null

    // Executor for HTTP downloads (bridge-initiated previews & saves)
    private val ioExecutor = Executors.newCachedThreadPool()

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

    // Launcher for ACTION_CREATE_DOCUMENT — user picks where to save
    private val createDocumentLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val uri = result.data?.data
        val url = pendingDownloadUrl
        pendingDownloadUrl = null
        pendingDownloadName = null
        if (result.resultCode != RESULT_OK || uri == null || url == null) {
            return@registerForActivityResult
        }
        Toast.makeText(this, "Descargando...", Toast.LENGTH_SHORT).show()
        ioExecutor.execute {
            try {
                val bytes = downloadBytes(url)
                contentResolver.openOutputStream(uri)?.use { out ->
                    out.write(bytes)
                }
                runOnUiThread {
                    Toast.makeText(this, "Archivo guardado", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Log.e("NodexSave", "Save failed: ${e.message}", e)
                runOnUiThread {
                    Toast.makeText(this, "Error al guardar: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
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
            isPullRefreshing = true
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
                // Only show spinner for explicit pull-to-refresh, not in-app navigation
                if (isPullRefreshing) swipeRefresh.isRefreshing = true
                view?.evaluateJavascript(HIDE_FLASHES_JS, null)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                isPullRefreshing = false
                offlineOverlay.visibility = View.GONE

                // Inject viewport meta if missing, mark as Android, and
                // bulletproof-hide any server-rendered flash messages.
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
                view?.evaluateJavascript(HIDE_FLASHES_JS, null)

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

        // Expose a JS bridge so the /documentos page can call into native
        // code for previews (Intent.ACTION_VIEW with a FileProvider Uri) and
        // downloads-with-picker (Intent.ACTION_CREATE_DOCUMENT).
        webView.addJavascriptInterface(NodexJSBridge(), "NodexAndroid")

        // Handle authenticated downloads (e.g. /documentos/<id>/download).
        // The WebView swallows Content-Disposition responses by default, so
        // we route them through the system DownloadManager and forward the
        // session cookie + user-agent so the Flask backend authorizes the
        // request.
        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            // On Android <= 9 we need WRITE_EXTERNAL_STORAGE to write into the
            // public Downloads folder. On Android 10+ scoped storage applies
            // and DownloadManager handles it for us.
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                if (checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    requestPermissions(
                        arrayOf(android.Manifest.permission.WRITE_EXTERNAL_STORAGE), 1002
                    )
                    Toast.makeText(
                        this,
                        "Concede permiso de almacenamiento y vuelve a pulsar Descargar",
                        Toast.LENGTH_LONG
                    ).show()
                    return@setDownloadListener
                }
            }

            try {
                val filename = URLUtil.guessFileName(url, contentDisposition, mimeType)
                val request = DownloadManager.Request(Uri.parse(url)).apply {
                    setMimeType(mimeType)
                    addRequestHeader("User-Agent", userAgent)
                    // Forward the WebView's session cookie so the backend
                    // recognizes the user.
                    val cookie = CookieManager.getInstance().getCookie(url)
                    if (!cookie.isNullOrEmpty()) {
                        addRequestHeader("Cookie", cookie)
                    }
                    setTitle(filename)
                    setDescription("Descargando desde NodexAI Panel")
                    setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                    )
                    setDestinationInExternalPublicDir(
                        Environment.DIRECTORY_DOWNLOADS, filename
                    )
                    allowScanningByMediaScanner()
                }

                val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)
                Toast.makeText(this, "Descargando $filename...", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Log.e("NodexDownload", "Download failed: ${e.message}", e)
                Toast.makeText(
                    this,
                    "Error al descargar: ${e.message}",
                    Toast.LENGTH_LONG
                ).show()
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
                val prefs = getSharedPreferences("nodexai", MODE_PRIVATE)
                prefs.edit().putString("fcm_token", token).apply()
                // Also clear any pending token saved by the background service
                prefs.edit().remove("pending_fcm_token").apply()
                sendTokenViaJs(webView, token)
            }
            .addOnFailureListener { e ->
                Log.e("NodexFCM", "Token error: ${e.message}")
                // Try to register any token the background service saved when
                // onNewToken fired without an active WebView session.
                val pending = getSharedPreferences("nodexai", MODE_PRIVATE)
                    .getString("pending_fcm_token", null)
                if (pending != null) {
                    sendTokenViaJs(webView, pending)
                }
            }
    }

    private fun sendTokenViaJs(webView: WebView?, token: String) {
        val escaped = token.replace("'", "\\'")
        webView?.evaluateJavascript("""
            fetch('/api/push/register', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token: '$escaped', platform: 'android'})
            }).then(function(r){ console.log('FCM register: ' + r.status); })
              .catch(function(e){ console.error('FCM register err: ' + e); });
        """.trimIndent(), null)
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

    // ─── JS bridge helpers ───────────────────────────────────────────

    /** Resolve a possibly-relative URL (e.g. /documentos/1/preview) into
     *  an absolute one using the WebView's current origin. */
    private fun resolveUrl(raw: String): String {
        return if (raw.startsWith("http://") || raw.startsWith("https://")) {
            raw
        } else {
            BASE_URL.trimEnd('/') + "/" + raw.trimStart('/')
        }
    }

    /** Blocking HTTP GET that forwards the WebView session cookie. */
    private fun downloadBytes(url: String): ByteArray {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 60000
        conn.instanceFollowRedirects = true
        val cookie = CookieManager.getInstance().getCookie(url)
        if (!cookie.isNullOrEmpty()) {
            conn.setRequestProperty("Cookie", cookie)
        }
        conn.setRequestProperty("User-Agent", webView.settings.userAgentString)
        try {
            conn.inputStream.use { return it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    /** Download the URL to cache/doc_preview/<name> and open with
     *  Intent.ACTION_VIEW via FileProvider so the user's preferred
     *  viewer (PDF reader, image viewer, etc.) handles it. */
    private fun openPreview(url: String, name: String, mime: String) {
        Toast.makeText(this, "Abriendo vista previa...", Toast.LENGTH_SHORT).show()
        ioExecutor.execute {
            try {
                val bytes = downloadBytes(url)
                val dir = File(cacheDir, "doc_preview").apply { mkdirs() }
                val safeName = name.replace("/", "_").ifBlank { "documento" }
                val file = File(dir, safeName)
                FileOutputStream(file).use { it.write(bytes) }

                val uri = FileProvider.getUriForFile(
                    this, "$packageName.fileprovider", file
                )
                val resolvedMime = mime.ifBlank { contentResolver.getType(uri) ?: "*/*" }
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, resolvedMime)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                runOnUiThread {
                    try {
                        startActivity(
                            Intent.createChooser(intent, "Abrir con")
                        )
                    } catch (e: Exception) {
                        Toast.makeText(
                            this,
                            "No hay app para abrir este archivo",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                Log.e("NodexPreview", "Preview failed: ${e.message}", e)
                runOnUiThread {
                    Toast.makeText(
                        this,
                        "Error al cargar vista previa: ${e.message}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    /** Launch ACTION_CREATE_DOCUMENT so the user picks where to save.
     *  The actual HTTP download happens in the launcher callback. */
    private fun launchSavePicker(url: String, name: String, mime: String) {
        pendingDownloadUrl = url
        pendingDownloadName = name
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = mime.ifBlank { "*/*" }
            putExtra(Intent.EXTRA_TITLE, name)
        }
        try {
            createDocumentLauncher.launch(intent)
        } catch (e: Exception) {
            pendingDownloadUrl = null
            pendingDownloadName = null
            Toast.makeText(
                this,
                "No se pudo abrir el selector: ${e.message}",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    /** JS interface exposed as `window.NodexAndroid` to the WebView.
     *  All methods marshal onto the UI thread because they launch
     *  activities or show toasts. */
    inner class NodexJSBridge {
        @JavascriptInterface
        fun previewDocument(url: String, name: String, mime: String) {
            val resolved = resolveUrl(url)
            runOnUiThread { openPreview(resolved, name, mime) }
        }

        @JavascriptInterface
        fun saveDocument(url: String, name: String) {
            val resolved = resolveUrl(url)
            runOnUiThread { launchSavePicker(resolved, name, "") }
        }
    }
}
