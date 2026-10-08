package com.adsearn.mobile.data

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Signature
import java.util.Base64

data class DeviceProof(val publicKey: String, val signature: String)

class DeviceIdentityStore {
    @Synchronized
    fun logout() {
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(KEY_ALIAS)
    }

    @Synchronized
    fun sign(deviceFingerprint: String, nonce: String): DeviceProof {
        val keyPair = getOrCreateKeyPair()
        val payload = "AdsEarn device session v1\n$deviceFingerprint\n$nonce".toByteArray(Charsets.US_ASCII)
        val signature = Signature.getInstance("SHA256withECDSA").run {
            initSign(keyPair.private)
            update(payload)
            sign()
        }
        val encoder = Base64.getUrlEncoder().withoutPadding()
        return DeviceProof(
            publicKey = encoder.encodeToString(keyPair.public.encoded),
            signature = encoder.encodeToString(signature),
        )
    }

    fun sessionRequestHash(
        packageName: String,
        deviceFingerprint: String,
        challengeId: String,
        nonce: String,
        publicKey: String,
    ): String {
        val request = listOf(
            "adsearn-session-v1", packageName, deviceFingerprint, challengeId, nonce, publicKey,
        ).joinToString("\n").toByteArray(Charsets.US_ASCII)
        return MessageDigest.getInstance("SHA-256").digest(request)
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }

    private fun getOrCreateKeyPair(): KeyPair {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.PrivateKeyEntry
        if (existing != null) return KeyPair(existing.certificate.publicKey, existing.privateKey)

        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        generator.initialize(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_SIGN)
                .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build(),
        )
        return generator.generateKeyPair()
    }

    private companion object {
        const val KEY_ALIAS = "adsearn_device_identity_v1"
    }
}
