package com.ori.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.pm.ServiceInfo
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.DisplayMetrics
import android.view.WindowManager
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class ScreenShareService : Service() {
    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var workerThread: HandlerThread? = null
    private var workerHandler: Handler? = null
    private val uploader = Executors.newSingleThreadExecutor()
    private val uploadBusy = AtomicBoolean(false)
    private var lastFrameAt = 0L
    private var baseUrl = ""
    private var token = ""

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        baseUrl = intent?.getStringExtra("base_url") ?: ""
        token = intent?.getStringExtra("token") ?: ""
        val resultCode = intent?.getIntExtra("result_code", 0) ?: 0
        val data = if (Build.VERSION.SDK_INT >= 33) intent?.getParcelableExtra("projection_data", Intent::class.java)
                   else @Suppress("DEPRECATION") intent?.getParcelableExtra("projection_data")
        if (baseUrl.isBlank() || token.isBlank() || data == null || resultCode == 0) {
            stopSelf(); return START_NOT_STICKY
        }
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(6034, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(6034, buildNotification())
        }
        startProjection(resultCode, data)
        return START_NOT_STICKY
    }

    private fun buildNotification(): Notification {
        val channelId = "ori_screen_share"
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(channelId, "ORI screen sharing", NotificationManager.IMPORTANCE_LOW))
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, channelId) else Notification.Builder(this)
        return builder.setContentTitle("ORI screen sharing is active")
            .setContentText("Your phone screen is shared only with your paired ORI desktop.")
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setOngoing(true)
            .build()
    }

    private fun startProjection(resultCode: Int, data: Intent) {
        try {
            val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projection = manager.getMediaProjection(resultCode, data)
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            (getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(metrics)
            val scale = minOf(1.0, 960.0 / metrics.widthPixels.toDouble())
            val width = maxOf(320, (metrics.widthPixels * scale).toInt())
            val height = maxOf(320, (metrics.heightPixels * scale).toInt())
            val density = metrics.densityDpi
            reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 3)
            workerThread = HandlerThread("ori-screen-capture").also { it.start() }
            workerHandler = Handler(workerThread!!.looper)
            reader!!.setOnImageAvailableListener({ source -> captureLatestFrame(source) }, workerHandler)
            projection!!.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() { stopSelf() }
            }, workerHandler)
            display = projection!!.createVirtualDisplay(
                "ORI Screen Share", width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader!!.surface, null, workerHandler
            )
        } catch (_: Exception) {
            stopSelf()
        }
    }

    private fun captureLatestFrame(source: ImageReader) {
        val now = System.currentTimeMillis()
        if (now - lastFrameAt < 850 || !uploadBusy.compareAndSet(false, true)) return
        lastFrameAt = now
        var image: Image? = null
        try {
            image = source.acquireLatestImage() ?: return
            val plane = image.planes[0]
            val pixelStride = plane.pixelStride
            val rowStride = plane.rowStride
            val rowPadding = rowStride - pixelStride * image.width
            val paddedWidth = image.width + rowPadding / pixelStride
            val bitmap = Bitmap.createBitmap(paddedWidth, image.height, Bitmap.Config.ARGB_8888)
            bitmap.copyPixelsFromBuffer(plane.buffer)
            val cropped = Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
            val output = ByteArrayOutputStream()
            cropped.compress(Bitmap.CompressFormat.JPEG, 48, output)
            bitmap.recycle(); cropped.recycle()
            val bytes = output.toByteArray()
            uploader.execute { uploadFrame(bytes) }
        } catch (_: Exception) {
            uploadBusy.set(false)
        } finally {
            image?.close()
        }
    }

    private fun uploadFrame(bytes: ByteArray) {
        var connection: HttpURLConnection? = null
        try {
            connection = (URL("$baseUrl/api/phone-screen/frame").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"; connectTimeout = 2500; readTimeout = 2500
                doOutput = true; setFixedLengthStreamingMode(bytes.size)
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Content-Type", "image/jpeg")
            }
            connection.outputStream.use { it.write(bytes) }
            connection.responseCode
        } catch (_: Exception) {
            // Frame uploads are opportunistic; the next capture retries.
        } finally {
            connection?.disconnect()
            uploadBusy.set(false)
        }
    }

    override fun onDestroy() {
        display?.release(); display = null
        reader?.close(); reader = null
        projection?.stop(); projection = null
        workerThread?.quitSafely(); workerThread = null; workerHandler = null
        uploader.shutdownNow()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
