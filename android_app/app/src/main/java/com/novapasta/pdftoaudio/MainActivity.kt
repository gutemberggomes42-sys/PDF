package com.novapasta.pdftoaudio

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.DownloadListener
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.URLUtil
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private val defaultBaseUrl = "https://nova-pasta-production-b55e.up.railway.app/"

    private val pickFiles = registerForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        val callback = filePathCallback
        filePathCallback = null
        if (callback == null) return@registerForActivityResult
        if (uris == null) {
            callback.onReceiveValue(null)
            return@registerForActivityResult
        }
        callback.onReceiveValue(uris.toTypedArray())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)

        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.userAgentString = settings.userAgentString + " PdfToAudioAndroid/1.0"

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return false
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback
                val types = fileChooserParams.acceptTypes.filter { it.isNotBlank() }.toTypedArray()
                val mimeTypes = if (types.isEmpty()) arrayOf("*/*") else types
                pickFiles.launch(mimeTypes)
                return true
            }
        }

        webView.setDownloadListener(DownloadListener { url, userAgent, contentDisposition, mimetype, contentLength ->
            val request = DownloadManager.Request(Uri.parse(url))
            request.setMimeType(mimetype)
            request.addRequestHeader("User-Agent", userAgent)
            try {
                val cookie = CookieManager.getInstance().getCookie(url)
                if (!cookie.isNullOrBlank()) {
                    request.addRequestHeader("Cookie", cookie)
                }
            } catch (e: Exception) {
            }
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, URLUtil.guessFileName(url, contentDisposition, mimetype))
            val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            dm.enqueue(request)
        })

        val prefs = getSharedPreferences("pdf_to_audio", MODE_PRIVATE)
        val key = "base_url"
        val baseUrl = prefs.getString(key, null)
        if (baseUrl.isNullOrBlank()) {
            prefs.edit().putString(key, defaultBaseUrl).apply()
            webView.loadUrl(defaultBaseUrl)
        } else {
            webView.loadUrl(baseUrl)
        }

        webView.setOnLongClickListener {
            promptBaseUrl { url ->
                prefs.edit().putString(key, url).apply()
                webView.loadUrl(url)
            }
            true
        }
    }

    private fun promptBaseUrl(onSaved: (String) -> Unit) {
        val prefs = getSharedPreferences("pdf_to_audio", MODE_PRIVATE)
        val key = "base_url"
        val current = prefs.getString(key, defaultBaseUrl) ?: defaultBaseUrl
        val input = android.widget.EditText(this)
        input.setText(current)
        AlertDialog.Builder(this)
            .setTitle("Servidor")
            .setMessage("URL do servidor (ex: https://SEU_DOMINIO/ ou http://SEU_IP:5000/)")
            .setView(input)
            .setPositiveButton("Salvar") { _, _ ->
                var url = input.text.toString().trim()
                if (!url.endsWith("/")) url += "/"
                onSaved(url)
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
