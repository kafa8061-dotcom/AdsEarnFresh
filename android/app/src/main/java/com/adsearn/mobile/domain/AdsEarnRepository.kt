package com.adsearn.mobile.domain

import com.adsearn.mobile.data.AdReservationResponse
import com.adsearn.mobile.data.AdsEarnApi
import com.adsearn.mobile.data.PhoneRequest
import com.adsearn.mobile.data.PreferencesRequest
import com.adsearn.mobile.data.ProfileRequest
import com.adsearn.mobile.data.SecureSessionStore
import com.adsearn.mobile.data.SessionRequest
import com.adsearn.mobile.data.SessionRequestFingerprint
import com.adsearn.mobile.data.DeviceIdentityStore
import com.adsearn.mobile.data.SupportRequest
import com.adsearn.mobile.data.SupportResponse
import com.adsearn.mobile.data.SupportTicketResponse
import com.adsearn.mobile.data.WalletResponse
import com.adsearn.mobile.data.WithdrawalRequest
import com.adsearn.mobile.data.WithdrawalResponse
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import retrofit2.HttpException

interface AdsEarnRepository {
    suspend fun openSession()
    suspend fun loadDashboard(): Dashboard
    suspend fun loadProfile(): Profile
    suspend fun saveProfile(request: ProfileRequest): Profile
    suspend fun reserveAd(): AdReservationResponse
    suspend fun cancelAd(reservationId: String)
    suspend fun loadWallet(): WalletResponse
    suspend fun loadWithdrawals(): List<WithdrawalResponse>
    suspend fun requestWithdrawal(amount: String): WithdrawalResponse
    suspend fun loadPaymentMethod(): com.adsearn.mobile.data.PaymentResponse?
    suspend fun savePaymentMethod(countryIso: String, phone: String): com.adsearn.mobile.data.PaymentResponse
    suspend fun loadNotifications(): List<com.adsearn.mobile.data.NotificationResponse>
    suspend fun loadPreferences(): PreferencesRequest
    suspend fun savePreferences(preferences: PreferencesRequest): PreferencesRequest
    suspend fun createTicket(category: String, description: String): SupportResponse
    suspend fun loadSupportTickets(): List<SupportTicketResponse>
    suspend fun logout()
}

class ApiRepository(
    private val api: AdsEarnApi,
    private val sessionStore: SecureSessionStore,
    private val deviceFingerprint: String,
    private val deviceIdentityStore: DeviceIdentityStore,
) : AdsEarnRepository {
    private val sessionMutex = Mutex()

    private suspend fun createBoundSession() {
        val challenge = api.createSessionChallenge(SessionRequestFingerprint(deviceFingerprint))
        val proof = deviceIdentityStore.sign(deviceFingerprint, challenge.nonce)
        sessionStore.accessToken = api.createSession(
            SessionRequest(deviceFingerprint, challenge.challenge_id, proof.publicKey, proof.signature),
        ).access_token
    }

    override suspend fun openSession() = sessionMutex.withLock {
        if (sessionStore.accessToken == null) {
            createBoundSession()
            return@withLock
        }
        try {
            api.dashboard()
        } catch (exception: retrofit2.HttpException) {
            if (exception.code() != 401) throw exception
            sessionStore.accessToken = null
            createBoundSession()
        }
    }

    override suspend fun loadDashboard() = api.dashboard().toDomain()
    override suspend fun loadProfile() = api.profile().toDomain()
    override suspend fun saveProfile(request: ProfileRequest) = api.saveProfile(request).toDomain()
    override suspend fun reserveAd() = api.reserveAd()
    override suspend fun cancelAd(reservationId: String) = api.cancelAd(reservationId)
    override suspend fun loadWallet() = api.wallet()
    override suspend fun loadWithdrawals() = api.withdrawals()
    override suspend fun requestWithdrawal(amount: String): WithdrawalResponse {
        val requestKey = sessionStore.withdrawalRequestKey(amount)
        return try {
            api.requestWithdrawal(WithdrawalRequest(amount, requestKey)).also {
                sessionStore.clearWithdrawalRequestKey()
            }
        } catch (exception: HttpException) {
            if (exception.code() in 400..499) sessionStore.clearWithdrawalRequestKey()
            throw exception
        }
    }
    override suspend fun loadPaymentMethod() = api.paymentMethod()
    override suspend fun savePaymentMethod(countryIso: String, phone: String) =
        api.savePaymentMethod(PhoneRequest(countryIso, phone))
    override suspend fun loadNotifications() = api.notifications()
    override suspend fun loadPreferences() = api.preferences()
    override suspend fun savePreferences(preferences: PreferencesRequest) = api.savePreferences(preferences)
    override suspend fun createTicket(category: String, description: String) =
        api.createSupportTicket(SupportRequest(category, description))
    override suspend fun loadSupportTickets() = api.supportTickets()

    override suspend fun logout() = sessionMutex.withLock {
        try {
            api.logout()
        } finally {
            sessionStore.accessToken = null
            sessionStore.clearWithdrawalRequestKey()
            deviceIdentityStore.logout()
        }
    }
}
