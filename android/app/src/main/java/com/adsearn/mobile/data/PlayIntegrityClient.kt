package com.adsearn.mobile.data

import android.content.Context
import android.os.SystemClock
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.StandardIntegrityManager
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.atomic.AtomicReference
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class PlayIntegrityClient(
    context: Context,
    private val cloudProjectNumber: Long,
) {
    private val manager = IntegrityManagerFactory.createStandard(context.applicationContext)
    private val preparationMutex = Mutex()
    private val tokenProvider = AtomicReference<PreparedTokenProvider?>(null)

    suspend fun requestToken(requestHash: String): String {
        require(cloudProjectNumber > 0) { "Play Integrity Cloud project number is not configured" }
        require(requestHash.matches(Regex("^[0-9a-f]{64}$"))) { "Invalid Play Integrity request hash" }
        val provider = tokenProvider.get()?.takeIf(::isFresh) ?: preparationMutex.withLock {
            tokenProvider.get()?.takeIf(::isFresh) ?: PreparedTokenProvider(
                manager.prepareIntegrityToken(
                    StandardIntegrityManager.PrepareIntegrityTokenRequest.builder()
                        .setCloudProjectNumber(cloudProjectNumber)
                        .build(),
                ).await(),
                SystemClock.elapsedRealtime(),
            ).also(tokenProvider::set)
        }
        return provider.provider.request(
            StandardIntegrityManager.StandardIntegrityTokenRequest.builder()
                .setRequestHash(requestHash)
                .build(),
        ).await().token()
    }

    private fun isFresh(provider: PreparedTokenProvider): Boolean =
        SystemClock.elapsedRealtime() - provider.preparedAtMillis < TOKEN_PROVIDER_REFRESH_INTERVAL_MILLIS

    private suspend fun <T> com.google.android.gms.tasks.Task<T>.await(): T =
        suspendCancellableCoroutine { continuation ->
            addOnSuccessListener { result ->
                if (continuation.isActive) continuation.resume(result)
            }
            addOnFailureListener { failure ->
                if (continuation.isActive) continuation.resumeWithException(failure)
            }
        }

    private data class PreparedTokenProvider(
        val provider: StandardIntegrityManager.StandardIntegrityTokenProvider,
        val preparedAtMillis: Long,
    )

    private companion object {
        const val TOKEN_PROVIDER_REFRESH_INTERVAL_MILLIS = 50 * 60 * 1000L
    }
}
