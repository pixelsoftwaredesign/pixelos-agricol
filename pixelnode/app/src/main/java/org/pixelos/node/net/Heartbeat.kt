// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.net

import android.content.Context
import android.net.wifi.WifiManager
import com.google.gson.Gson
import kotlinx.coroutines.*
import org.pixelos.node.PixelNodeApp
import java.io.IOException
import java.net.*
import java.util.concurrent.atomic.AtomicInteger

data class HeartbeatMessage(
    val node_id: String,
    val node_type: String = "mobile",
    val status: String = "active",
    val battery: Int,
    val peers: Int,
    val uptime: Long,
    val version: String = "1.0.0",
    val timestamp: Long = System.currentTimeMillis()
)

class Heartbeat(private val context: Context) {
    companion object {
        private const val PORT = 9100
        private const val INTERVAL_MS = 60_000L
        private const val BROADCAST_ADDR = "255.255.255.255"
    }

    private var job: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val gson = Gson()
    private val peers = AtomicInteger(0)

    fun start() {
        job = scope.launch {
            val wifi = context.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val multicastLock = wifi.createMulticastLock("pixelnode_heartbeat")
            multicastLock.acquire()
            try {
                while (isActive) {
                    sendHeartbeat()
                    delay(INTERVAL_MS)
                }
            } finally {
                try { multicastLock.release() } catch (_: Exception) {}
            }
        }
    }

    private fun sendHeartbeat() {
        try {
            val app = PixelNodeApp.instance
            val msg = HeartbeatMessage(
                node_id = app.pixKey.nodeId(),
                battery = getBatteryLevel(),
                peers = peers.get(),
                uptime = System.currentTimeMillis() - startTime
            )
            val data = gson.toJson(msg).toByteArray()
            val socket = DatagramSocket().apply { broadcast = true }
            val packet = DatagramPacket(data, data.size, InetAddress.getByName(BROADCAST_ADDR), PORT)
            socket.send(packet)
            socket.close()
        } catch (e: IOException) {
            // ignore
        }
    }

    fun updatePeers(count: Int) = peers.set(count)

    fun stop() {
        job?.cancel()
        scope.cancel()
    }

    private var startTime = System.currentTimeMillis()

    private fun getBatteryLevel(): Int {
        return try {
            val intent = context.registerReceiver(null, android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
            val level = intent?.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = intent?.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1) ?: -1
            if (level > 0 && scale > 0) (level * 100) / scale else -1
        } catch (_: Exception) { -1 }
    }

    fun getUptime(): Long = System.currentTimeMillis() - startTime
}
