package com.adsearn.mobile.ui

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.adsearn.mobile.AdsEarnApplication
import com.adsearn.mobile.data.NotificationResponse
import com.adsearn.mobile.data.PaymentResponse
import com.adsearn.mobile.data.PreferencesRequest
import com.adsearn.mobile.data.ProfileRequest
import com.adsearn.mobile.data.SupportResponse
import com.adsearn.mobile.data.SupportTicketResponse
import com.adsearn.mobile.data.WithdrawalResponse
import com.adsearn.mobile.domain.Dashboard
import com.adsearn.mobile.domain.Profile
import com.adsearn.mobile.domain.Wallet
import com.adsearn.mobile.domain.toDomain
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

data class AppUiState(
    val sessionReady: Boolean = false,
    val signedOut: Boolean = false,
    val isBusy: Boolean = false,
    val dashboard: Dashboard? = null,
    val profile: Profile? = null,
    val wallet: Wallet? = null,
    val withdrawals: List<WithdrawalResponse> = emptyList(),
    val paymentMethod: PaymentResponse? = null,
    val notifications: List<NotificationResponse> = emptyList(),
    val supportTickets: List<SupportTicketResponse> = emptyList(),
    val preferences: PreferencesRequest? = null,
    val notice: String? = null,
    val error: String? = null,
    val theme: String = "System",
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = (application as AdsEarnApplication).repository
    private val preferenceStore = application.getSharedPreferences("adsearn_preferences", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(AppUiState(theme = preferenceStore.getString("theme", "System") ?: "System"))
    val state: StateFlow<AppUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            try {
                repository.openSession()
                _state.update { it.copy(sessionReady = true, signedOut = false) }
                refreshDashboard()
            } catch (exception: IOException) {
                _state.update { it.copy(error = "Unable to connect right now. Check your connection and try again.") }
            } catch (exception: HttpException) {
                _state.update { it.copy(error = userMessage(exception)) }
            }
        }
    }

    fun retryConnection() {
        viewModelScope.launch {
            _state.update { it.copy(isBusy = true, error = null) }
            try {
                repository.openSession()
                _state.update { it.copy(sessionReady = true, signedOut = false) }
                refreshDashboard()
            } catch (exception: IOException) {
                _state.update { it.copy(error = "Unable to connect right now. Check your connection and try again.") }
            } catch (exception: HttpException) {
                _state.update { it.copy(error = userMessage(exception)) }
            } finally {
                _state.update { it.copy(isBusy = false) }
            }
        }
    }

    fun refreshDashboard() {
        request({ repository.loadDashboard() }) { state, dashboard -> state.copy(dashboard = dashboard) }
    }

    fun loadProfile() = request({ repository.loadProfile() }) { state, profile -> state.copy(profile = profile) }

    fun saveProfile(fullName: String, email: String, countryIso: String, phone: String) =
        request({ repository.saveProfile(ProfileRequest(fullName.trim(), email.trim(), countryIso, phone.trim())) }) { state, profile ->
                state.copy(profile = profile, dashboard = state.dashboard?.copy(name = profile.fullName), notice = "Profile saved successfully.")
            }

    suspend fun reserveAd() = repository.reserveAd()

    fun finishAdReservation(reservationId: String, earned: Boolean) {
        if (!earned) {
            request({ repository.cancelAd(reservationId) }) { state, _ -> state }
        }
    }

    fun onAdRewardCallback() {
        viewModelScope.launch {
            repeat(10) {
                try {
                    val dashboard = repository.loadDashboard()
                    val previous = _state.value.dashboard?.dailyAds ?: 0
                    _state.update { it.copy(dashboard = dashboard) }
                    if (dashboard.dailyAds > previous) {
                        _state.update { it.copy(notice = "Your rewarded ad completion was verified.") }
                        return@launch
                    }
                } catch (exception: IOException) {
                    _state.update { it.copy(error = "Ad completion is awaiting server verification.") }
                    return@launch
                } catch (exception: HttpException) {
                    _state.update { it.copy(error = userMessage(exception)) }
                    return@launch
                }
                delay(1_500)
            }
            _state.update { it.copy(notice = "Ad watched. Activity appears after backend verification.") }
        }
    }

    fun loadWallet() = request({ repository.loadWallet() }) { state, wallet -> state.copy(wallet = wallet.toDomain()) }

    fun loadWithdrawals() = request({ repository.loadWithdrawals() }) { state, withdrawals -> state.copy(withdrawals = withdrawals) }

    fun requestWithdrawal(amount: String) {
        request(
            { repository.requestWithdrawal(amount.trim()) },
            transform = { state, withdrawal ->
                state.copy(
                    withdrawals = listOf(withdrawal) + state.withdrawals,
                    notice = "Your withdrawal request has been submitted and is pending review.",
                )
            },
            afterSuccess = {
                runCatchingRefresh()
            },
        )
    }

    fun loadPaymentMethod() = request({ repository.loadPaymentMethod() }) { state, payment -> state.copy(paymentMethod = payment) }

    fun savePaymentMethod(countryIso: String, phone: String) =
        request({ repository.savePaymentMethod(countryIso, phone.trim()) }) { state, payment ->
            state.copy(paymentMethod = payment, notice = "WAAFI payment method saved successfully.")
        }

    fun loadNotifications() = request({ repository.loadNotifications() }) { state, notifications -> state.copy(notifications = notifications) }

    fun loadPreferences() = request({ repository.loadPreferences() }) { state, preferences -> state.copy(preferences = preferences) }

    fun savePreferences(preferences: PreferencesRequest) =
        request({ repository.savePreferences(preferences) }) { state, saved ->
            state.copy(preferences = saved, notice = "Notification preferences saved.")
        }

    fun createSupportTicket(category: String, description: String) =
        request(
            { repository.createTicket(category, description.trim()) },
            afterSuccess = {
                val tickets = repository.loadSupportTickets()
                _state.update { state -> state.copy(supportTickets = tickets) }
            },
        ) { state, _: SupportResponse ->
            state.copy(notice = "Your support ticket has been created successfully.")
        }

    fun loadSupportTickets() = request({ repository.loadSupportTickets() }) { state, tickets ->
        state.copy(supportTickets = tickets)
    }

    fun setTheme(theme: String) {
        preferenceStore.edit().putString("theme", theme).apply()
        _state.update { it.copy(theme = theme) }
    }

    fun logout() {
        viewModelScope.launch {
            _state.update { it.copy(isBusy = true) }
            try {
                repository.logout()
                _state.update {
                    it.copy(
                        sessionReady = false, signedOut = true, dashboard = null, profile = null, wallet = null,
                        withdrawals = emptyList(), paymentMethod = null, notifications = emptyList(),
                        supportTickets = emptyList(),
                        notice = "Your secure session has been revoked.",
                    )
                }
            } catch (exception: IOException) {
                _state.update {
                    it.copy(
                        sessionReady = false, signedOut = true, dashboard = null, profile = null, wallet = null,
                        withdrawals = emptyList(), paymentMethod = null, notifications = emptyList(),
                        supportTickets = emptyList(),
                        error = "Your session was cleared on this device, but server sign-out could not be confirmed.",
                    )
                }
            } catch (exception: HttpException) {
                _state.update {
                    it.copy(
                        sessionReady = false, signedOut = true, dashboard = null, profile = null, wallet = null,
                        withdrawals = emptyList(), paymentMethod = null, notifications = emptyList(),
                        supportTickets = emptyList(),
                        error = userMessage(exception),
                    )
                }
            } finally {
                _state.update { it.copy(isBusy = false) }
            }
        }
    }

    fun clearMessages() {
        _state.update { it.copy(notice = null, error = null) }
    }

    fun reportError(message: String) {
        _state.update { it.copy(error = message) }
    }

    fun reportNotice(message: String) {
        _state.update { it.copy(notice = message) }
    }

    private fun <T> request(
        block: suspend () -> T,
        afterSuccess: suspend (T) -> Unit = {},
        transform: (AppUiState, T) -> AppUiState,
    ) {
        viewModelScope.launch {
            _state.update { it.copy(isBusy = true, error = null) }
            try {
                val result = block()
                _state.update { current -> transform(current, result) }
                afterSuccess(result)
            } catch (exception: IOException) {
                _state.update { it.copy(error = "Unable to connect right now. Check your connection and try again.") }
            } catch (exception: HttpException) {
                _state.update { it.copy(error = userMessage(exception)) }
            } finally {
                _state.update { it.copy(isBusy = false) }
            }
        }
    }

    private fun userMessage(exception: HttpException): String = when (exception.code()) {
        401 -> "Your secure session has expired. Please try again."
        409 -> exception.response()?.errorBody()?.string()?.let(::extractDetail) ?: "This action is not available for your account right now."
        429 -> "You've reached today's limit. Come back tomorrow."
        else -> "We couldn't complete that request. Please try again."
    }

    private fun extractDetail(body: String): String {
        val detail = Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(body)?.groupValues?.getOrNull(1)
        return detail ?: "This action is not available for your account right now."
    }

    private suspend fun runCatchingRefresh() {
        try {
            val wallet = repository.loadWallet().toDomain()
            val withdrawals = repository.loadWithdrawals()
            _state.update { it.copy(wallet = wallet, withdrawals = withdrawals) }
        } catch (exception: IOException) {
            _state.update { it.copy(error = "Your request was submitted. Wallet details will refresh when you're online.") }
        } catch (exception: HttpException) {
            _state.update { it.copy(error = userMessage(exception)) }
        }
    }
}
