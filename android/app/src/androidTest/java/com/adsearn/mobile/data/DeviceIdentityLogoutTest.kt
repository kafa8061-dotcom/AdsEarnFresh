package com.adsearn.mobile.data

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceIdentityLogoutTest {
    @Test
    fun logoutDeletesTheKeyThatCouldReopenThePreviousAnonymousAccount() {
        val identity = DeviceIdentityStore()
        val previousKey = identity.sign("device-fingerprint", "first-nonce").publicKey

        identity.logout()

        val nextKey = identity.sign("device-fingerprint", "second-nonce").publicKey
        assertNotEquals(previousKey, nextKey)
    }
}
