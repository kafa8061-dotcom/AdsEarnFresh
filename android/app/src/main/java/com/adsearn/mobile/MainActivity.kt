package com.adsearn.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.adsearn.mobile.ui.AdsEarnNavigation
import com.adsearn.mobile.ui.AppViewModel
import com.adsearn.mobile.ui.theme.AdsEarnTheme
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform

class MainActivity : ComponentActivity() {
    private val viewModel: AppViewModel by viewModels()
    private val ads by lazy { (application as AdsEarnApplication).rewardedAdManager }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestAdsConsent()
        setContent {
            val state = viewModel.state.collectAsStateWithLifecycle()
            AdsEarnTheme(state.value.theme) {
                AdsEarnNavigation(viewModel = viewModel, rewardedAdManager = ads)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        ads.preload()
    }

    override fun onDestroy() {
        if (isFinishing) ads.release()
        super.onDestroy()
    }

    private fun requestAdsConsent() {
        val consentInformation = UserMessagingPlatform.getConsentInformation(this)
        val parameters = ConsentRequestParameters.Builder().build()
        consentInformation.requestConsentInfoUpdate(
            this,
            parameters,
            {
                UserMessagingPlatform.loadAndShowConsentFormIfRequired(this) {
                    if (consentInformation.canRequestAds()) ads.initialize()
                }
            },
            {
                if (consentInformation.canRequestAds()) ads.initialize()
            },
        )
    }
}
