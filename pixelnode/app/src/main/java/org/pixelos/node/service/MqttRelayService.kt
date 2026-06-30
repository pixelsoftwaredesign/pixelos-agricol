// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.service

import android.content.Context
import com.google.gson.Gson
import org.eclipse.paho.android.service.MqttAndroidClient
import org.eclipse.paho.client.mqttv3.*
import org.pixelos.node.PixelNodeApp
import kotlinx.coroutines.*

class MqttRelayService(private val context: Context) {
    companion object {
        private const val RELAY_TOPICS = "sensors/#,robots/+/status,alerts/+,heartbeat/#"
    }

    private var client: MqttAndroidClient? = null
    private val gson = Gson()
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    fun connect(brokerUrl: String = "tcp://10.0.0.1:1883") {
        val app = PixelNodeApp.instance
        val clientId = "pixelnode-${app.pixKey.nodeId()}"
        client = MqttAndroidClient(context, brokerUrl, clientId)

        client?.setCallback(object : MqttCallbackExtended {
            override fun connectComplete(reconnect: Boolean, serverURI: String) {
                subscribeToRelayTopics()
            }

            override fun connectionLost(cause: Throwable?) {
                scope.launch {
                    delay(10_000)
                    reconnect()
                }
            }

            override fun messageArrived(topic: String?, message: MqttMessage?) {
                if (topic != null && message != null) {
                    relayMessage(topic, message)
                }
            }

            override fun deliveryComplete(token: IMqttDeliveryToken?) {}
        })

        try {
            client?.connect(createConnectionOptions())
        } catch (_: Exception) {}
    }

    private fun createConnectionOptions(): MqttConnectOptions {
        return MqttConnectOptions().apply {
            isAutomaticReconnect = true
            keepAliveInterval = 30
            cleanSession = true
        }
    }

    private fun subscribeToRelayTopics() {
        try {
            client?.subscribe(RELAY_TOPICS, 1)
        } catch (_: Exception) {}
    }

    private fun relayMessage(topic: String, message: MqttMessage) {
        scope.launch {
            try {
                client?.publish(topic, message.payload, 1, false)
            } catch (_: Exception) {}
        }
    }

    private suspend fun reconnect() {
        try {
            client?.connect(createConnectionOptions())
        } catch (_: Exception) {}
    }

    fun disconnect() {
        try {
            client?.disconnect()
            client?.close()
        } catch (_: Exception) {}
        scope.cancel()
    }
}
