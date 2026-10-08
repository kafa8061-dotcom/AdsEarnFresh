package com.adsearn.mobile.domain

import com.adsearn.mobile.data.DashboardResponse
import com.adsearn.mobile.data.ProfileResponse
import com.adsearn.mobile.data.WalletResponse
import java.math.BigDecimal

data class Dashboard(
    val name: String?,
    val userId: String,
    val dailyAds: Int,
    val dailyLimit: Int,
    val availableBalance: BigDecimal,
    val currency: String,
)

data class Profile(
    val fullName: String?,
    val email: String?,
    val phone: String?,
    val countryIso: String?,
    val countryCode: String?,
    val userId: String,
)

data class Wallet(
    val balance: BigDecimal,
    val currency: String,
    val transactions: List<com.adsearn.mobile.data.TransactionResponse>,
)

fun DashboardResponse.toDomain() = Dashboard(
    name = user_name,
    userId = user_id,
    dailyAds = daily_ads,
    dailyLimit = daily_limit,
    availableBalance = available_balance.toBigDecimalOrNull() ?: BigDecimal.ZERO,
    currency = currency,
)

fun ProfileResponse.toDomain() = Profile(full_name, email, phone, country_iso, country_code, user_id)

fun WalletResponse.toDomain() = Wallet(
    balance = available_balance.toBigDecimalOrNull() ?: BigDecimal.ZERO,
    currency = currency,
    transactions = transactions,
)
