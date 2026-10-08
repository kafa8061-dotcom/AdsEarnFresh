package com.adsearn.mobile.ads

import android.app.Activity
import android.content.Context
import android.os.Handler
import android.os.Looper
import com.adsearn.mobile.BuildConfig
import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.OnUserEarnedRewardListener
import com.google.android.gms.ads.rewarded.RewardedAd
import com.google.android.gms.ads.rewarded.RewardedAdLoadCallback
import com.google.android.gms.ads.rewarded.ServerSideVerificationOptions
import com.google.android.gms.ads.MobileAds
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.atomic.AtomicBoolean

class RewardedAdManager(context: Context) {
    private val applicationContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private var initialized = false
    private var loading = false
    private var released = false
    private var rewardedAd: RewardedAd? = null
    private val _isReady = MutableStateFlow(false)
    val isReady: StateFlow<Boolean> = _isReady.asStateFlow()
    private val retryLoad = Runnable { load() }

    fun initialize() {
        if (initialized) return
        initialized = true
        MobileAds.initialize(applicationContext) { handler.post { load() } }
    }

    fun preload() {
        if (initialized && rewardedAd == null) load()
    }

    private fun load() {
        if (!initialized || rewardedAd != null || loading || released) return
        loading = true
        RewardedAd.load(
            applicationContext,
            BuildConfig.REWARDED_AD_UNIT_ID,
            AdRequest.Builder().build(),
            object : RewardedAdLoadCallback() {
                override fun onAdLoaded(ad: RewardedAd) {
                    loading = false
                    if (released) return
                    rewardedAd = ad
                    _isReady.value = true
                }

                override fun onAdFailedToLoad(error: LoadAdError) {
                    loading = false
                    rewardedAd = null
                    _isReady.value = false
                    handler.removeCallbacks(retryLoad)
                    handler.postDelayed(retryLoad, RETRY_MILLIS)
                }
            },
        )
    }

    fun show(
        activity: Activity,
        reservationId: String,
        userId: String,
        onRewarded: () -> Unit,
        onFinished: (earned: Boolean) -> Unit,
    ) {
        val ad = rewardedAd
        if (ad == null) {
            _isReady.value = false
            onFinished(false)
            load()
            return
        }

        rewardedAd = null
        _isReady.value = false
        val completionSent = AtomicBoolean(false)
        var rewardReceived = false
        fun finish() {
            if (completionSent.compareAndSet(false, true)) onFinished(rewardReceived)
        }

        ad.setServerSideVerificationOptions(
            ServerSideVerificationOptions.Builder()
                .setCustomData(reservationId)
                .setUserId(userId)
                .build(),
        )
        ad.fullScreenContentCallback = object : FullScreenContentCallback() {
            override fun onAdDismissedFullScreenContent() {
                finish()
                load()
            }

            override fun onAdFailedToShowFullScreenContent(error: AdError) {
                finish()
                load()
            }
        }
        ad.show(activity, OnUserEarnedRewardListener {
            if (!rewardReceived) {
                rewardReceived = true
                onRewarded()
            }
        })
    }

    fun release() {
        released = true
        loading = false
        handler.removeCallbacksAndMessages(null)
        rewardedAd = null
        _isReady.value = false
    }

    private companion object {
        const val RETRY_MILLIS = 30_000L
    }
}
