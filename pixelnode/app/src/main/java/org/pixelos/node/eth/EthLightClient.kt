// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.eth

import org.web3j.protocol.Web3j
import org.web3j.protocol.http.HttpService
import org.web3j.protocol.core.DefaultBlockParameterName
import java.math.BigInteger
import kotlinx.coroutines.*

data class WalletState(
    val address: String = "",
    val balance: BigInteger = BigInteger.ZERO,
    val latestBlock: BigInteger = BigInteger.ZERO,
    val peers: Int = 0
)

class EthLightClient(private val rpcUrl: String = "https://rpc.gnosischain.com") {
    private var web3j: Web3j? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var _state = WalletState()
    val state: WalletState get() = _state

    fun connect() {
        try {
            web3j = Web3j.build(HttpService(rpcUrl))
            scope.launch { pollStatus() }
        } catch (_: Exception) {}
    }

    private suspend fun pollStatus() {
        while (isActive) {
            try {
                val blockNumber = web3j?.ethBlockNumber()?.send()?.blockNumber ?: BigInteger.ZERO
                _state = _state.copy(latestBlock = blockNumber)
            } catch (_: Exception) {}
            delay(30_000L)
        }
    }

    fun getBalance(address: String): BigInteger {
        return try {
            web3j?.ethGetBalance(address, DefaultBlockParameterName.LATEST)?.send()?.balance ?: BigInteger.ZERO
        } catch (_: Exception) { BigInteger.ZERO }
    }

    fun disconnect() {
        scope.cancel()
        web3j?.shutdown()
    }

    fun isConnected(): Boolean = web3j != null
}
