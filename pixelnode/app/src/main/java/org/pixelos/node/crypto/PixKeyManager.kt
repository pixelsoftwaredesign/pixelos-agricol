// Pixel OS - Copyright 2026
// Free License - Verifiable and Reliable for Internet Users
package org.pixelos.node.crypto

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey

class PixKeyManager(private val context: Context) {
    companion object {
        private const val KEYSTORE_ALIAS = "pixelnode_identity"
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }

    private val keyStore: KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun getOrCreateKeyPair(): KeyStore.Entry? {
        if (keyStore.containsAlias(KEYSTORE_ALIAS)) {
            return keyStore.getEntry(KEYSTORE_ALIAS, null)
        }
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
        generator.initialize(
            KeyGenParameterSpec.Builder(KEYSTORE_ALIAS, KeyProperties.PURPOSE_SIGN)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256k1"))
                .build()
        )
        generator.generateKeyPair()
        return keyStore.getEntry(KEYSTORE_ALIAS, null)
    }

    fun getPublicKey(): PublicKey? {
        return (keyStore.getEntry(KEYSTORE_ALIAS, null) as? KeyStore.PrivateKeyEntry)?.certificate?.publicKey
    }

    fun getPrivateKey(): PrivateKey? {
        return (keyStore.getEntry(KEYSTORE_ALIAS, null) as? KeyStore.PrivateKeyEntry)?.privateKey
    }

    fun nodeId(): String {
        val pub = getPublicKey() ?: return "unknown"
        return pub.hashCode().toUInt().toString(16).padStart(8, '0')
    }
}
