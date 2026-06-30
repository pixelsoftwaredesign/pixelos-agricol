package org.pixelos.node

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import org.pixelos.node.crypto.PixKeyManager

class PixelNodeApp : Application() {
    companion object {
        const val CHANNEL_NODE = "pixelnode_service"
        const val CHANNEL_WALLET = "pixelnode_wallet"
        lateinit var instance: PixelNodeApp
    }

    lateinit var pixKey: PixKeyManager

    override fun onCreate() {
        super.onCreate()
        instance = this
        pixKey = PixKeyManager(this)
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_NODE, "Service nœud", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Notification persistante du nœud Pixel OS"
                setShowBadge(false)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_WALLET, "Portefeuille", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Notifications de transactions BITROOT"
            }
        )
    }
}
