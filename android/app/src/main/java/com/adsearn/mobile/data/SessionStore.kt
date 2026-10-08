package com.adsearn.mobile.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class SecureSessionStore(context: Context) {
    private val preferences = EncryptedSharedPreferences.create(
        context,
        "adsearn_secure_session",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    var accessToken: String?
        get() = preferences.getString("access_token", null)
        set(value) {
            preferences.edit().putString("access_token", value).apply()
        }

    fun withdrawalRequestKey(amount: String): String {
        val savedAmount = preferences.getString("pending_withdrawal_amount", null)
        val savedKey = preferences.getString("pending_withdrawal_key", null)
        if (savedAmount == amount && savedKey != null) return savedKey
        val newKey = UUID.randomUUID().toString()
        preferences.edit()
            .putString("pending_withdrawal_amount", amount)
            .putString("pending_withdrawal_key", newKey)
            .apply()
        return newKey
    }

    fun clearWithdrawalRequestKey() {
        preferences.edit()
            .remove("pending_withdrawal_amount")
            .remove("pending_withdrawal_key")
            .apply()
    }
}
