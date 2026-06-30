// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import org.pixelos.node.MainActivity
import org.pixelos.node.PixelNodeApp
import org.pixelos.node.R
import org.pixelos.node.eth.EthLightClient
import org.pixelos.node.net.Heartbeat
import org.pixelos.node.net.PixDht

class PixelNodeService : Service() {
    companion object {
        private const val NOTIFICATION_ID = 1001
        var isRunning = false; private set
        var peersCount = 0; private set
        var ethBlock = 0L; private set

        fun start(ctx: Context) {
            val intent = Intent(ctx, PixelNodeService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(intent)
            } else {
                ctx.startService(intent)
            }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, PixelNodeService::class.java))
        }
    }

    private lateinit var heartbeat: Heartbeat
    private lateinit var dht: PixDht
    private lateinit var mqttRelay: MqttRelayService
    private lateinit var ethClient: EthLightClient
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        heartbeat = Heartbeat(this)
        dht = PixDht()
        mqttRelay = MqttRelayService(this)
        ethClient = EthLightClient()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        isRunning = true
        startForeground(NOTIFICATION_ID, createNotification("DÃ©marrage..."))
        acquireWakeLock()

        heartbeat.start()
        mqttRelay.connect()
        ethClient.connect()
        dht.bootstrap(listOf("10.0.0.1" to 9100))

        updateNotification()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        isRunning = false
        heartbeat.stop()
        mqttRelay.disconnect()
        ethClient.disconnect()
        dht.clear()
        releaseWakeLock()
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pixelnode:wakelock")
        wakeLock?.acquire(30 * 60 * 1000L)
    }

    private fun releaseWakeLock() {
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
    }

    private fun updateNotification() {
        val peers = dht.peerCount()
        peersCount = peers
        heartbeat.updatePeers(peers)
        val block = ethClient.state.latestBlock.toLong()
        ethBlock = block

        val notification = createNotification("$peers pairs Â· bloc $block")
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, notification)

        // Refresh every 30s while running
        android.os.Handler(mainLooper).postDelayed({ if (isRunning) updateNotification() }, 30_000)
    }

    private fun createNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, PixelNodeApp.CHANNEL_NODE)
            .setContentTitle("PixelNode Â· ${PixelNodeApp.instance.pixKey.nodeId()}")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }
}
