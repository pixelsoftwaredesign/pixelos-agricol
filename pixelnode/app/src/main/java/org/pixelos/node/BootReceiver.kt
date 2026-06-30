// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import org.pixelos.node.service.PixelNodeService

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            PixelNodeService.start(context)
        }
    }
}
