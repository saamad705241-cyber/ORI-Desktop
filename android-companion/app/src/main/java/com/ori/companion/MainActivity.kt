package com.ori.companion

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var baseUrl: EditText
    private lateinit var pairingCode: EditText
    private lateinit var status: TextView
    private lateinit var shareButton: Button
    private var pairedToken: String? = null
    private val projectionRequest = 4107

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        val prefs = getSharedPreferences("ori_companion", Context.MODE_PRIVATE)
        baseUrl.setText(prefs.getString("base_url", ""))
        pairedToken = prefs.getString("token_encrypted", null)?.let { TokenVault.decrypt(it) }
        if (!pairedToken.isNullOrBlank()) {
            status.text = "PAIRED · READY TO SHARE"
            shareButton.isEnabled = true
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 36, 28, 28)
            setBackgroundColor(0xFF06100A.toInt())
        }
        fun label(text: String, size: Float = 13f) = TextView(this).apply {
            this.text = text; textSize = size; setTextColor(0xFF48F79A.toInt())
            setPadding(0, 12, 0, 8)
        }
        baseUrl = EditText(this).apply {
            hint = "ORI address, e.g. https://192.168.1.5:8000"
            setSingleLine(true); setTextColor(0xFFE4F6EA.toInt()); setHintTextColor(0xFF72917C.toInt())
        }
        pairingCode = EditText(this).apply {
            hint = "8-character companion code"; setSingleLine(true)
            setTextColor(0xFFE4F6EA.toInt()); setHintTextColor(0xFF72917C.toInt())
        }
        status = label("NOT PAIRED", 12f)
        val pairButton = Button(this).apply { text = "PAIR WITH ORI" }
        shareButton = Button(this).apply { text = "SHARE PHONE SCREEN"; isEnabled = false }
        val stopButton = Button(this).apply { text = "STOP SHARING" }
        root.addView(label("ORI SCREEN COMPANION", 22f))
        root.addView(label("Secure, user-approved screen sharing to your paired ORI desktop."))
        root.addView(label("ORI SERVER ADDRESS")); root.addView(baseUrl)
        root.addView(label("ONE-TIME PAIRING CODE")); root.addView(pairingCode)
        root.addView(pairButton); root.addView(status)
        root.addView(shareButton); root.addView(stopButton)
        root.addView(label("Your phone shows Android's native screen-capture consent dialog. Sharing stops when you press STOP or revoke Android's permission."))
        setContentView(root)

        pairButton.setOnClickListener { pairDevice() }
        shareButton.setOnClickListener { requestScreenCapture() }
        stopButton.setOnClickListener {
            stopService(Intent(this, ScreenShareService::class.java))
            status.text = "SCREEN SHARING STOPPED"
        }
    }

    private fun pairDevice() {
        val base = baseUrl.text.toString().trim().trimEnd('/')
        val code = pairingCode.text.toString().trim().uppercase()
        if (!(base.startsWith("https://") || base.startsWith("http://")) || code.length != 8) {
            Toast.makeText(this, "Enter the ORI URL and 8-character code", Toast.LENGTH_LONG).show()
            return
        }
        status.text = "PAIRING…"
        worker.execute {
            try {
                val connection = (URL("$base/api/companion/pair").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"; connectTimeout = 5000; readTimeout = 7000
                    doOutput = true; setRequestProperty("Content-Type", "application/json")
                }
                connection.outputStream.use { it.write(JSONObject().put("code", code).toString().toByteArray()) }
                val body = (if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream)
                    .bufferedReader().use { it.readText() }
                val json = JSONObject(body)
                if (!json.optBoolean("ok")) throw IllegalStateException(json.optString("error", "Pairing failed"))
                val token = json.getString("token")
                getSharedPreferences("ori_companion", Context.MODE_PRIVATE).edit()
                    .putString("base_url", base)
                    .putString("token_encrypted", TokenVault.encrypt(token))
                    .apply()
                pairedToken = token
                runOnUiThread {
                    status.text = "PAIRED · SCREEN SHARING AVAILABLE"
                    shareButton.isEnabled = true
                }
            } catch (error: Exception) {
                runOnUiThread { status.text = "PAIRING FAILED · ${error.message ?: error.javaClass.simpleName}" }
            }
        }
    }

    private fun requestScreenCapture() {
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        startActivityForResult(manager.createScreenCaptureIntent(), projectionRequest)
    }

    @Deprecated("Android MediaProjection activity result is required by the platform API")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != projectionRequest) return
        if (resultCode != Activity.RESULT_OK || data == null) {
            status.text = "SCREEN CAPTURE PERMISSION DENIED"
            return
        }
        val token = pairedToken ?: run { status.text = "PAIR WITH ORI FIRST"; return }
        val base = baseUrl.text.toString().trim().trimEnd('/')
        val service = Intent(this, ScreenShareService::class.java).apply {
            putExtra("result_code", resultCode)
            putExtra("projection_data", data)
            putExtra("base_url", base)
            putExtra("token", token)
        }
        startForegroundService(service)
        status.text = "SCREEN SHARING · ORI CAN ANALYZE ON REQUEST"
    }
}
