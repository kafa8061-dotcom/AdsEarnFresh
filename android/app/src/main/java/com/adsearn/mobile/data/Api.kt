package com.adsearn.mobile.data

import com.adsearn.mobile.BuildConfig
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path

data class SessionResponse(val access_token: String, val user_id: String)
data class SessionRequest(val device_fingerprint: String)
data class DashboardResponse(
    val user_name: String?,
    val user_id: String,
    val daily_ads: Int,
    val daily_limit: Int,
    val available_balance: String,
    val currency: String,
)
data class ProfileRequest(
    val full_name: String,
    val email: String,
    val country_iso: String,
    val phone: String,
)
data class ProfileResponse(
    val full_name: String?,
    val email: String?,
    val phone: String?,
    val country_iso: String?,
    val country_code: String?,
    val user_id: String,
)
data class PhoneRequest(val country_iso: String, val phone: String)
data class PaymentResponse(val country_iso: String, val country_code: String, val phone_last4: String)
data class AdReservationResponse(
    val reservation_id: String,
    val user_id: String,
    val ad_unit_id: String,
    val daily_count: Int,
    val daily_limit: Int,
)
data class TransactionResponse(
    val transaction_id: String,
    val transaction_type: String,
    val amount: String,
    val status: String,
    val created_at: String,
)
data class WalletResponse(val available_balance: String, val currency: String, val transactions: List<TransactionResponse>)
data class WithdrawalRequest(val amount: String, val request_key: String)
data class WithdrawalResponse(
    val withdrawal_id: String,
    val amount: String,
    val status: String,
    val payment_method: String,
    val payment_reference: String?,
    val created_at: String,
)
data class SupportRequest(val category: String, val description: String)
data class SupportResponse(val ticket_id: String, val status: String)
data class SupportMessageResponse(val sender: String, val body: String, val created_at: String)
data class SupportTicketResponse(
    val ticket_id: String,
    val category: String,
    val description: String,
    val status: String,
    val created_at: String,
    val messages: List<SupportMessageResponse>,
)
data class PreferencesRequest(
    val daily_ads: Boolean,
    val withdrawals: Boolean,
    val support: Boolean,
    val account: Boolean,
)
data class NotificationResponse(
    val notification_id: String,
    val category: String,
    val title: String,
    val body: String,
    val read: Boolean,
    val created_at: String,
)

interface AdsEarnApi {
    @POST("v1/session")
    suspend fun createSession(@Body request: SessionRequest): SessionResponse
    @POST("v1/session/logout")
    suspend fun logout()
    @GET("v1/dashboard")
    suspend fun dashboard(): DashboardResponse
    @GET("v1/profile")
    suspend fun profile(): ProfileResponse
    @PUT("v1/profile")
    suspend fun saveProfile(@Body profile: ProfileRequest): ProfileResponse
    @POST("v1/ads/reservations")
    suspend fun reserveAd(): AdReservationResponse
    @DELETE("v1/ads/reservations/{reservationId}")
    suspend fun cancelAd(@Path("reservationId") reservationId: String)
    @GET("v1/wallet")
    suspend fun wallet(): WalletResponse
    @GET("v1/withdrawals")
    suspend fun withdrawals(): List<WithdrawalResponse>
    @POST("v1/withdrawals")
    suspend fun requestWithdrawal(@Body request: WithdrawalRequest): WithdrawalResponse
    @GET("v1/payment-method")
    suspend fun paymentMethod(): PaymentResponse?
    @PUT("v1/payment-method")
    suspend fun savePaymentMethod(@Body request: PhoneRequest): PaymentResponse
    @GET("v1/notifications")
    suspend fun notifications(): List<NotificationResponse>
    @GET("v1/notification-preferences")
    suspend fun preferences(): PreferencesRequest
    @PUT("v1/notification-preferences")
    suspend fun savePreferences(@Body request: PreferencesRequest): PreferencesRequest
    @POST("v1/support")
    suspend fun createSupportTicket(@Body request: SupportRequest): SupportResponse
    @GET("v1/support/tickets")
    suspend fun supportTickets(): List<SupportTicketResponse>
}

object NetworkClient {
    fun create(sessionStore: SecureSessionStore): AdsEarnApi {
        val sessionInterceptor = Interceptor { chain ->
            val request = chain.request().newBuilder().apply {
                sessionStore.accessToken?.let { header("Authorization", "Bearer $it") }
            }.build()
            chain.proceed(request)
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(sessionInterceptor)
            .connectTimeout(java.time.Duration.ofSeconds(15))
            .readTimeout(java.time.Duration.ofSeconds(20))
            .writeTimeout(java.time.Duration.ofSeconds(20))
            .build()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(AdsEarnApi::class.java)
    }
}
