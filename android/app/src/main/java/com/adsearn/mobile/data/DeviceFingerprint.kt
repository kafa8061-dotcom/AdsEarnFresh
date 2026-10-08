package com.adsearn.mobile.data

import android.content.Context
import android.provider.Settings
import java.security.MessageDigest

fun Context.deviceFingerprint(): String {
    val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
        ?: error("This device does not provide a stable app identifier")
    val digest = MessageDigest.getInstance("SHA-256")
        .digest("AdsEarn-device-v1:$androidId".toByteArray(Charsets.UTF_8))
    return digest.joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
}
