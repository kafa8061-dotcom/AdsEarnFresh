package com.adsearn.mobile

import android.app.Application
import com.adsearn.mobile.data.NetworkClient
import com.adsearn.mobile.data.DeviceIdentityStore
import com.adsearn.mobile.data.SecureSessionStore
import com.adsearn.mobile.data.deviceFingerprint
import com.adsearn.mobile.ads.RewardedAdManager
import com.adsearn.mobile.domain.ApiRepository

class AdsEarnApplication : Application() {
    lateinit var sessionStore: SecureSessionStore
        private set
    lateinit var repository: ApiRepository
        private set
    lateinit var deviceIdentityStore: DeviceIdentityStore
        private set
    lateinit var rewardedAdManager: RewardedAdManager
        private set

    override fun onCreate() {
        super.onCreate()
        sessionStore = SecureSessionStore(this)
        deviceIdentityStore = DeviceIdentityStore()
        repository = ApiRepository(
            NetworkClient.create(sessionStore), sessionStore, deviceFingerprint(), deviceIdentityStore,
        )
        rewardedAdManager = RewardedAdManager(this)
    }
}
