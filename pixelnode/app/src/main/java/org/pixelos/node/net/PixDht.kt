// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.net

import java.net.InetAddress
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

data class PeerInfo(
    val nodeId: String,
    val address: InetAddress,
    val port: Int = 9100,
    val lastSeen: Long = System.currentTimeMillis(),
    val status: String = "active"
)

class PixDht {
    companion object {
        const val MAX_BUCKET_SIZE = 8
        const val PEER_TIMEOUT_MS = 300_000L // 5 min
        const val REPLICATION_FACTOR = 3
    }

    private val routingTable = ConcurrentHashMap<Int, MutableList<PeerInfo>>()
    private val peers = CopyOnWriteArrayList<PeerInfo>()

    fun bootstrap(seedNodes: List<Pair<String, Int>>) {
        for ((addr, port) in seedNodes) {
            try {
                val peer = PeerInfo(nodeId = "seed", address = InetAddress.getByName(addr), port = port)
                peers.add(peer)
                addToBucket(peer)
            } catch (_: Exception) {}
        }
    }

    fun addPeer(nodeId: String, addr: InetAddress, port: Int = 9100) {
        val existing = peers.find { it.nodeId == nodeId }
        if (existing != null) {
            peers.remove(existing)
        }
        val peer = PeerInfo(nodeId = nodeId, address = addr, port = port)
        peers.add(peer)
        addToBucket(peer)
        evictStalePeers()
    }

    private fun addToBucket(peer: PeerInfo) {
        val bucketIndex = distanceBucket(peer.nodeId.hashCode())
        val bucket = routingTable.getOrPut(bucketIndex) { mutableListOf() }
        synchronized(bucket) {
            if (!bucket.any { it.nodeId == peer.nodeId }) {
                if (bucket.size >= MAX_BUCKET_SIZE) {
                    bucket.removeAt(0)
                }
                bucket.add(peer)
            }
        }
    }

    fun findPeers(nodeId: String, count: Int = REPLICATION_FACTOR): List<PeerInfo> {
        val targetHash = nodeId.hashCode()
        return peers
            .filter { it.nodeId != nodeId }
            .sortedBy { it.nodeId.hashCode() xor targetHash }
            .take(count)
    }

    fun getAlivePeers(): List<PeerInfo> {
        val now = System.currentTimeMillis()
        return peers.filter { now - it.lastSeen < PEER_TIMEOUT_MS }
    }

    fun peerCount(): Int = getAlivePeers().size

    private fun evictStalePeers() {
        val now = System.currentTimeMillis()
        peers.removeAll { now - it.lastSeen > PEER_TIMEOUT_MS }
    }

    private fun distanceBucket(hash: Int): Int {
        if (hash == 0) return 0
        return (0 until 32).first { (hash ushr it) and 1 == 1 }
    }

    fun clear() {
        peers.clear()
        routingTable.clear()
    }
}
