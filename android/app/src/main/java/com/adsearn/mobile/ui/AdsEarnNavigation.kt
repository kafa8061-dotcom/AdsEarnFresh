package com.adsearn.mobile.ui

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import android.app.Activity
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.AccountBalanceWallet
import androidx.compose.material.icons.rounded.Campaign
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SupportAgent
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.adsearn.mobile.ads.RewardedAdManager
import com.adsearn.mobile.data.NotificationResponse
import com.adsearn.mobile.data.PreferencesRequest
import com.adsearn.mobile.data.WithdrawalResponse
import com.adsearn.mobile.domain.Dashboard
import com.adsearn.mobile.domain.Profile
import com.adsearn.mobile.domain.Wallet
import com.google.i18n.phonenumbers.PhoneNumberUtil
import com.google.android.ump.ConsentInformation
import com.google.android.ump.UserMessagingPlatform
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException
import java.math.BigDecimal
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale
import kotlinx.coroutines.delay

private const val HOME = "home"
private const val ADS = "ads"
private const val WALLET = "wallet"
private const val PROFILE = "profile"
private const val PAYMENT = "payment"
private const val NOTIFICATIONS = "notifications"
private const val SUPPORT = "support"
private const val SETTINGS = "settings"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdsEarnNavigation(viewModel: AppViewModel, rewardedAdManager: RewardedAdManager) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val isAdReady by rewardedAdManager.isReady.collectAsState()
    var route by rememberSaveable { mutableStateOf(HOME) }
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var splashVisible by rememberSaveable { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        delay(750)
        splashVisible = false
    }

    BackHandler(enabled = route != HOME) {
        route = if (route in listOf(PAYMENT, NOTIFICATIONS, SUPPORT, SETTINGS)) PROFILE else HOME
    }

    LaunchedEffect(route, state.sessionReady) {
        if (!state.sessionReady) return@LaunchedEffect
        when (route) {
            HOME -> {
                viewModel.refreshDashboard()
                viewModel.loadWallet()
            }
            WALLET -> {
                viewModel.loadWallet()
                viewModel.loadWithdrawals()
                viewModel.loadPaymentMethod()
            }
            PROFILE -> viewModel.loadProfile()
            PAYMENT -> viewModel.loadPaymentMethod()
            NOTIFICATIONS -> viewModel.loadNotifications()
            SUPPORT -> viewModel.loadSupportTickets()
            SETTINGS -> viewModel.loadPreferences()
        }
    }

    LaunchedEffect(state.notice, state.error) {
        val message = state.notice ?: state.error
        if (message != null) {
            snackbar.showSnackbar(message)
            viewModel.clearMessages()
        }
    }

    if (splashVisible) {
        BrandSplash(error = state.error, busy = state.isBusy, retry = viewModel::retryConnection)
        return
    }

    val titles = mapOf(
        HOME to "AdsEarn",
        ADS to "Watch ads",
        WALLET to "Your wallet",
        PROFILE to "Your profile",
        PAYMENT to "Payment method",
        NOTIFICATIONS to "Notifications",
        SUPPORT to "Contact support",
        SETTINGS to "Settings",
    )
    Scaffold(
        contentWindowInsets = WindowInsets.statusBars,
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        BrandMark(Modifier.size(34.dp))
                        Text(titles[route] ?: "AdsEarn", fontWeight = FontWeight.SemiBold, fontSize = 19.sp)
                    }
                },
                navigationIcon = {
                    if (route in listOf(PAYMENT, NOTIFICATIONS, SUPPORT, SETTINGS)) {
                        IconButton(onClick = { route = PROFILE }) {
                            Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back to profile")
                        }
                    }
                },
                actions = {
                    if (!state.signedOut && route !in listOf(NOTIFICATIONS, SETTINGS)) {
                        IconButton(onClick = { route = NOTIFICATIONS }) {
                            Icon(Icons.Rounded.Notifications, contentDescription = "Notifications")
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar(windowInsets = WindowInsets.navigationBars) {
                listOf(
                    Triple(HOME, "Home", Icons.Rounded.Home),
                    Triple(ADS, "Watch Ads", Icons.Rounded.Campaign),
                    Triple(WALLET, "Wallet", Icons.Rounded.AccountBalanceWallet),
                    Triple(PROFILE, "Profile", Icons.Rounded.Person),
                ).forEach { (destination, label, icon) ->
                    NavigationBarItem(
                        selected = route == destination,
                        onClick = { route = destination },
                        enabled = !state.signedOut || destination == HOME,
                        icon = { Icon(icon, contentDescription = label) },
                        label = { Text(label, maxLines = 1) },
                    )
                }
            }
        },
    ) { padding ->
        AnimatedContent(
            targetState = route,
            modifier = Modifier.padding(padding),
            transitionSpec = {
                (fadeIn() + slideInHorizontally { it / 16 }) togetherWith
                    (fadeOut() + slideOutHorizontally { -it / 16 })
            },
            label = "main-navigation",
        ) { destination ->
            when (destination) {
                HOME -> HomeScreen(
                    state.dashboard, state.wallet, state.error, state.isBusy, state.signedOut,
                    { route = ADS }, viewModel::retryConnection,
                )
                ADS -> WatchAdsScreen(
                    dashboard = state.dashboard,
                    adReady = isAdReady,
                    busy = state.isBusy || !state.sessionReady,
                    onWatch = {
                        scope.launch {
                            try {
                                val reservation = viewModel.reserveAd()
                                rewardedAdManager.show(
                                    activity = context as android.app.Activity,
                                    reservationId = reservation.reservation_id,
                                    userId = reservation.user_id,
                                    onRewarded = viewModel::onAdRewardCallback,
                                    onFinished = { earned ->
                                        viewModel.finishAdReservation(reservation.reservation_id, earned)
                                    },
                                )
                            } catch (exception: HttpException) {
                                viewModel.reportError(
                                    when (exception.code()) {
                                        429 -> "You've reached today's limit. Come back tomorrow."
                                        503 -> "No advertisement is available right now. Please try again later."
                                        else -> "We couldn't start an advertisement. Please try again later."
                                    },
                                )
                            } catch (exception: IOException) {
                                viewModel.reportError("Unable to connect right now. Please try again later.")
                            }
                        }
                    },
                    onWallet = { route = WALLET },
                )
                WALLET -> WalletScreen(
                    wallet = state.wallet,
                    withdrawals = state.withdrawals,
                    paymentAvailable = state.paymentMethod != null,
                    onRefresh = { viewModel.loadWallet(); viewModel.loadWithdrawals(); viewModel.loadPaymentMethod() },
                    onWithdraw = viewModel::requestWithdrawal,
                    onPayment = { route = PAYMENT },
                )
                PROFILE -> ProfileScreen(
                    profile = state.profile,
                    busy = state.isBusy,
                    onSave = viewModel::saveProfile,
                    onPayment = { route = PAYMENT },
                    onNotifications = { route = NOTIFICATIONS },
                    onSupport = { route = SUPPORT },
                    onSettings = { route = SETTINGS },
                )
                PAYMENT -> PaymentScreen(
                    payment = state.paymentMethod,
                    busy = state.isBusy,
                    onSave = viewModel::savePaymentMethod,
                )
                NOTIFICATIONS -> NotificationScreen(state.notifications, viewModel::loadNotifications)
                SUPPORT -> SupportScreen(
                    tickets = state.supportTickets,
                    busy = state.isBusy,
                    onSubmit = viewModel::createSupportTicket,
                    onRefresh = viewModel::loadSupportTickets,
                )
                SETTINGS -> SettingsScreen(
                    preferences = state.preferences,
                    theme = state.theme,
                    busy = state.isBusy,
                    onPreferences = viewModel::savePreferences,
                    onTheme = viewModel::setTheme,
                    onLogout = {
                        viewModel.logout()
                        route = HOME
                    },
                    onPrivacyOptions = {
                        val activity = context as? Activity
                        if (activity == null) {
                            viewModel.reportError("Privacy choices are unavailable right now.")
                        } else {
                            val consentInformation = UserMessagingPlatform.getConsentInformation(activity)
                            if (consentInformation.privacyOptionsRequirementStatus ==
                                ConsentInformation.PrivacyOptionsRequirementStatus.REQUIRED
                            ) {
                                UserMessagingPlatform.showPrivacyOptionsForm(activity) { error ->
                                    if (error != null) viewModel.reportError("Unable to open privacy choices right now.")
                                }
                            } else {
                                viewModel.reportNotice("No additional privacy choices are currently required.")
                            }
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun BrandSplash(error: String?, busy: Boolean, retry: () -> Unit) {
    Box(
        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp)) {
            BrandMark(Modifier.size(76.dp))
            Text("AdsEarn", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text("Simple. Transparent. Yours.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (error == null) {
                CircularProgressIndicator()
                Text("Opening your secure home", style = MaterialTheme.typography.bodySmall)
            } else {
                Text("You can keep using AdsEarn when your connection is ready.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Button(onClick = retry, enabled = !busy) {
                    if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else Text("Try again")
                }
            }
        }
    }
}

@Composable
private fun BrandMark(modifier: Modifier = Modifier) {
    Box(
        modifier.clip(RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.primary),
        contentAlignment = Alignment.Center,
    ) {
        Text("A", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 20.sp)
    }
}

@Composable
private fun HomeScreen(
    dashboard: Dashboard?,
    wallet: Wallet?,
    error: String?,
    busy: Boolean,
    signedOut: Boolean,
    onWatch: () -> Unit,
    onRetry: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 26.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (signedOut) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Your secure session is closed.", fontWeight = FontWeight.SemiBold)
                        Text("Open a new anonymous session when you're ready to continue.")
                        Button(onClick = onRetry, enabled = !busy) { Text("Open secure session") }
                    }
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    dashboard?.userNameGreeting() ?: "Welcome to AdsEarn",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text("Your account activity, clearly in one place.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (error != null) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("We couldn't refresh your account.", color = MaterialTheme.colorScheme.onErrorContainer)
                        OutlinedButton(onClick = onRetry) { Text("Try again") }
                    }
                }
            }
        }
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary),
                shape = RoundedCornerShape(24.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
            ) {
                Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    Text("Available balance", color = Color.White.copy(alpha = 0.78f), style = MaterialTheme.typography.titleMedium)
                    Text(
                        dashboard?.let { formatMoney(it.availableBalance, it.currency) } ?: "—",
                        color = Color.White,
                        fontSize = 34.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "Withdrawable funds are shown only when recorded by AdsEarn.",
                        color = Color.White.copy(alpha = 0.8f),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricCard(
                    title = "Daily ads",
                    value = dashboard?.let { "${it.dailyAds}/${it.dailyLimit}" } ?: "—",
                    modifier = Modifier.weight(1f),
                    accent = MaterialTheme.colorScheme.primary,
                )
                MetricCard(
                    title = "Recent activity",
                    value = wallet?.transactions?.size?.toString() ?: "—",
                    modifier = Modifier.weight(1f),
                    accent = MaterialTheme.colorScheme.secondary,
                )
            }
        }
        item {
            dashboard?.let {
                Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("User ID", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.height(4.dp))
                            Text(it.userId, fontWeight = FontWeight.SemiBold)
                        }
                        Text("Informational only", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        item {
            Button(
                onClick = onWatch,
                modifier = Modifier.fillMaxWidth().height(56.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Watch Ads", fontWeight = FontWeight.SemiBold)
            }
        }
        item {
            SectionHeading("Recent activity")
            when {
                wallet == null && busy -> LoadingRow()
                wallet?.transactions.isNullOrEmpty() -> EmptyCard("No transactions yet", "Your real account activity will appear here.")
                else -> wallet?.transactions?.take(3)?.forEach { TransactionRow(it) }
            }
        }
    }
}

private fun Dashboard.userNameGreeting(): String = name?.takeIf { it.isNotBlank() }?.let { "Hello, $it" } ?: "Welcome to AdsEarn"

@Composable
private fun WatchAdsScreen(
    dashboard: Dashboard?,
    adReady: Boolean,
    busy: Boolean,
    onWatch: () -> Unit,
    onWallet: () -> Unit,
) {
    val reachedLimit = dashboard != null && dashboard.dailyAds >= dashboard.dailyLimit
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Daily Ads", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                Text(
                    dashboard?.let { "${it.dailyAds}/${it.dailyLimit}" } ?: "—",
                    fontSize = 38.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
                Text("Only server-verified rewarded completions count toward your daily usage.")
            }
        }
        if (reachedLimit) {
            Text("You've reached today's limit. Come back tomorrow.", color = MaterialTheme.colorScheme.error)
        } else {
            Text("Ads are optional. Tap WATCH AD when one is available.")
        }
        Button(
            onClick = onWatch,
            enabled = adReady && !busy && !reachedLimit,
            modifier = Modifier.fillMaxWidth().height(58.dp),
            shape = RoundedCornerShape(18.dp),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(20.dp), color = MaterialTheme.colorScheme.onPrimary, strokeWidth = 2.dp)
            else {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(if (reachedLimit) "LIMIT REACHED" else "WATCH AD")
            }
        }
        if (!adReady && !reachedLimit) {
            Text(
                "No advertisement is available right now. Please try again later.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        Text(
            "An ad completion is not a cash reward. Publisher revenue, activity records, and your withdrawable wallet are separate.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedButton(onClick = onWallet, modifier = Modifier.fillMaxWidth()) { Text("View wallet") }
    }
}

@Composable
private fun WalletScreen(
    wallet: Wallet?,
    withdrawals: List<WithdrawalResponse>,
    paymentAvailable: Boolean,
    onRefresh: () -> Unit,
    onWithdraw: (String) -> Unit,
    onPayment: () -> Unit,
) {
    var showWithdrawal by rememberSaveable { mutableStateOf(false) }
    var amount by rememberSaveable { mutableStateOf("") }
    if (showWithdrawal) {
        AlertDialog(
            onDismissRequest = { showWithdrawal = false },
            title = { Text("Request a withdrawal") },
            text = {
                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it.filter { char -> char.isDigit() || char == '.' } },
                    label = { Text("Amount") },
                    prefix = { Text("$ ") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = { onWithdraw(amount); showWithdrawal = false },
                    enabled = amount.toBigDecimalOrNull()?.let { it > BigDecimal.ZERO } == true,
                ) { Text("Submit request") }
            },
            dismissButton = { TextButton(onClick = { showWithdrawal = false }) { Text("Cancel") } },
        )
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Available balance", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        wallet?.let { formatMoney(it.balance, it.currency) } ?: "—",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Button(
                        onClick = { if (paymentAvailable) showWithdrawal = true else onPayment() },
                        enabled = !paymentAvailable || (wallet != null && wallet.balance > BigDecimal.ZERO),
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp),
                    ) { Text(if (paymentAvailable) "Withdraw" else "Add WAAFI payment method") }
                    if (wallet?.balance == BigDecimal.ZERO) {
                        Text("No funds are currently eligible for withdrawal.", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            SectionHeading("Transaction history")
            TextButton(onClick = onRefresh) { Text("Refresh") }
        } }
        if (wallet == null) {
            item { LoadingRow() }
        } else if (wallet.transactions.isEmpty()) {
            item { EmptyCard("No transactions yet", "Only backend-recorded wallet entries are shown here.") }
        } else {
            items(wallet.transactions, key = { it.transaction_id }) { TransactionRow(it) }
        }
        item { SectionHeading("Withdrawal history") }
        if (withdrawals.isEmpty()) {
            item { EmptyCard("No withdrawals yet", "Submitted requests and their current status appear here.") }
        } else {
            items(withdrawals, key = { it.withdrawal_id }) { WithdrawalRow(it) }
        }
    }
}

@Composable
private fun ProfileScreen(
    profile: Profile?,
    busy: Boolean,
    onSave: (String, String, String, String) -> Unit,
    onPayment: () -> Unit,
    onNotifications: () -> Unit,
    onSupport: () -> Unit,
    onSettings: () -> Unit,
) {
    var fullName by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var countryIso by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    var loadedProfileId by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(profile?.userId) {
        if (profile != null && loadedProfileId != profile.userId) {
            fullName = profile.fullName.orEmpty()
            email = profile.email.orEmpty()
            countryIso = profile.countryIso.orEmpty()
            phone = profile.phone?.let { nationalPhone(it, profile.countryIso) }.orEmpty()
            loadedProfileId = profile.userId
        }
    }
    LazyColumn(
        Modifier.fillMaxSize().imePadding(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text("Your details", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("Your profile is private to your secure account.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            OutlinedTextField(fullName, { fullName = it }, Modifier.fillMaxWidth(), label = { Text("Full name") }, singleLine = true)
        }
        item {
            OutlinedTextField(
                email, { email = it }, Modifier.fillMaxWidth(), label = { Text("Email") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), singleLine = true,
            )
        }
        item {
            CountryPhoneFields(countryIso, phone, "Phone", { countryIso = it }, { phone = it })
        }
        item {
            Button(
                onClick = { onSave(fullName, email, countryIso, phone) },
                enabled = !busy && fullName.isNotBlank() && email.contains("@") && countryIso.isNotBlank() && phone.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(15.dp),
            ) { Text("Save Profile") }
        }
        profile?.let { saved ->
            item {
                Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text("User ID", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(saved.userId, fontWeight = FontWeight.SemiBold)
                            Text("Generated by AdsEarn · informational only", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
        item { SectionHeading("More") }
        item { ActionRow(Icons.Rounded.AccountBalanceWallet, "Payment method", "Add or update WAAFI", onPayment) }
        item { ActionRow(Icons.Rounded.Notifications, "Notifications", "Account activity and preferences", onNotifications) }
        item { ActionRow(Icons.Rounded.SupportAgent, "Support", "Contact the AdsEarn support team", onSupport) }
        item { ActionRow(Icons.Rounded.Settings, "Settings", "Notifications, theme, and session", onSettings) }
    }
}

@Composable
private fun PaymentScreen(
    payment: com.adsearn.mobile.data.PaymentResponse?,
    busy: Boolean,
    onSave: (String, String) -> Unit,
) {
    var countryIso by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(payment?.country_iso) {
        payment?.let {
            countryIso = it.country_iso
            phone = ""
        }
    }
    Column(
        Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text("WAAFI payment method", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("Your number is encrypted on the server and shown masked outside payment processing.")
        Card(shape = RoundedCornerShape(20.dp)) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                CountryPhoneFields(countryIso, phone, "WAAFI phone", { countryIso = it }, { phone = it })
                payment?.let {
                    Text("Saved number: ${it.country_code} •••• ${it.phone_last4}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Button(
                    onClick = { onSave(countryIso, phone) },
                    enabled = !busy && countryIso.isNotBlank() && phone.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                ) { Text("Save WAAFI payment method") }
            }
        }
        Text("Payments are processed only for approved withdrawals; saving a number does not initiate a transfer.")
    }
}

@Composable
private fun NotificationScreen(notifications: List<NotificationResponse>, onRefresh: () -> Unit) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Your updates", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                TextButton(onClick = onRefresh) { Text("Refresh") }
            }
        }
        if (notifications.isEmpty()) {
            item { EmptyCard("You're all caught up", "Backend notifications will appear here.") }
        } else {
            items(notifications, key = { it.notification_id }) { notification ->
                Card(shape = RoundedCornerShape(17.dp)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(notification.title, fontWeight = FontWeight.SemiBold)
                        Text(notification.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(formatDate(notification.created_at), style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

@Composable
private fun SupportScreen(
    tickets: List<com.adsearn.mobile.data.SupportTicketResponse>,
    busy: Boolean,
    onSubmit: (String, String) -> Unit,
    onRefresh: () -> Unit,
) {
    var category by rememberSaveable { mutableStateOf("Technical Problem") }
    var description by rememberSaveable { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    val categories = listOf("Withdrawal", "Payment Method", "Wallet", "Account", "Advertisements", "Technical Problem", "Other")
    Column(
        Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("How can we help?", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("Create a support ticket. Your ticket ID and OPEN status are assigned by AdsEarn.")
        Box {
            OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) { Text(category) }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                categories.forEach {
                    DropdownMenuItem(text = { Text(it) }, onClick = { category = it; expanded = false })
                }
            }
        }
        OutlinedTextField(
            description, { description = it.take(4000) },
            Modifier.fillMaxWidth().height(180.dp),
            label = { Text("Description") },
            minLines = 5,
        )
        Button(
            onClick = { onSubmit(category, description) },
            enabled = !busy && description.trim().length >= 10,
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
        ) { Text("Create support ticket") }
        val context = LocalContext.current
        TextButton(onClick = {
            context.startActivity(Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:adsearn13@gmail.com")))
        }) { Text("Email adsearn13@gmail.com") }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            SectionHeading("Your tickets")
            TextButton(onClick = onRefresh) { Text("Refresh") }
        }
        if (tickets.isEmpty()) {
            EmptyCard("No support tickets yet", "Tickets and replies from AdsEarn support appear here.")
        } else {
            tickets.forEach { ticket ->
                Card(shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(ticket.ticket_id, fontWeight = FontWeight.SemiBold)
                        Text("${ticket.category} · ${ticket.status}")
                        Text(ticket.description, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        ticket.messages.forEach { message ->
                            Text("${message.sender}: ${message.body}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsScreen(
    preferences: PreferencesRequest?,
    theme: String,
    busy: Boolean,
    onPreferences: (PreferencesRequest) -> Unit,
    onTheme: (String) -> Unit,
    onLogout: () -> Unit,
    onPrivacyOptions: () -> Unit,
) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Settings", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold) }
        item { SectionHeading("Notifications") }
        val current = preferences
        if (current == null) {
            item { LoadingRow() }
        } else {
            item {
                PreferenceSwitch("Daily Ads", "Up to 10 valid rewarded ads today", current.daily_ads) {
                    onPreferences(current.copy(daily_ads = it))
                }
            }
            item { PreferenceSwitch("Withdrawals", "Request and payment status updates", current.withdrawals) {
                onPreferences(current.copy(withdrawals = it))
            } }
            item { PreferenceSwitch("Support", "Ticket and support updates", current.support) {
                onPreferences(current.copy(support = it))
            } }
            item { PreferenceSwitch("Account", "Profile and security notices", current.account) {
                onPreferences(current.copy(account = it))
            } }
        }
        item { SectionHeading("Appearance") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Light", "Dark", "System").forEach { option ->
                    FilterChip(
                        selected = theme == option,
                        onClick = { onTheme(option) },
                        label = { Text(option) },
                    )
                }
            }
        }
        item {
            OutlinedButton(onClick = onLogout, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                Text("Log out")
            }
        }
        item {
            TextButton(onClick = onPrivacyOptions, modifier = Modifier.fillMaxWidth()) {
                Text("Privacy choices")
            }
        }
        item {
            Text(
                "Log out revokes your active session and removes its device key. A later anonymous session starts a new account; the old profile cannot be recovered.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun PreferenceSwitch(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Card(shape = RoundedCornerShape(16.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Medium)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Switch(checked = checked, onCheckedChange = onChange)
        }
    }
}

@Composable
private fun CountryPhoneFields(
    countryIso: String,
    phone: String,
    label: String,
    onCountryChange: (String) -> Unit,
    onPhoneChange: (String) -> Unit,
) {
    var showPicker by rememberSaveable { mutableStateOf(false) }
    val country = Countries.byIso(countryIso)
    if (showPicker) {
        CountryPickerDialog(
            onDismiss = { showPicker = false },
            onSelected = {
                onCountryChange(it.iso)
                showPicker = false
            },
        )
    }
    Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
        Text("Country", style = MaterialTheme.typography.labelLarge)
        OutlinedButton(
            onClick = { showPicker = true },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
        ) {
            Text(
                country?.let { "${it.flag}  ${it.name}   ${it.callingCode}" } ?: "Choose a country",
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Text("Country Code · automatic", style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.width(82.dp).height(56.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(country?.callingCode ?: "+—", fontWeight = FontWeight.SemiBold)
                }
            }
            OutlinedTextField(
                value = phone,
                onValueChange = { onPhoneChange(it.filter { char -> char.isDigit() || char == ' ' || char == '-' || char == '(' || char == ')' }.take(24)) },
                modifier = Modifier.weight(1f),
                label = { Text(label) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                singleLine = true,
                enabled = country != null,
            )
        }
        Text("The calling code is filled from your selected country.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun CountryPickerDialog(onDismiss: () -> Unit, onSelected: (CountryOption) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    val filtered = remember(query) {
        Countries.all.filter {
            it.name.contains(query, ignoreCase = true) ||
                it.iso.contains(query, ignoreCase = true) ||
                it.callingCode.contains(query)
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Choose a country") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    query, { query = it },
                    Modifier.fillMaxWidth(),
                    label = { Text("Search countries") },
                    singleLine = true,
                )
                LazyColumn(Modifier.height(360.dp)) {
                    items(filtered, key = { it.iso }) { country ->
                        Row(
                            Modifier.fillMaxWidth().clickable { onSelected(country) }.padding(vertical = 11.dp, horizontal = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(country.flag, fontSize = 22.sp)
                            Spacer(Modifier.width(12.dp))
                            Text(country.name, modifier = Modifier.weight(1f))
                            Text(country.callingCode, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        HorizontalDivider()
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
}

@Composable
private fun MetricCard(title: String, value: String, modifier: Modifier = Modifier, accent: Color) {
    Card(modifier, shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = accent)
        }
    }
}

@Composable
private fun SectionHeading(title: String) {
    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
}

@Composable
private fun EmptyCard(title: String, message: String) {
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(
            Modifier.fillMaxWidth().padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun LoadingRow() {
    Box(Modifier.fillMaxWidth().padding(22.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(Modifier.size(26.dp), strokeWidth = 2.dp)
    }
}

@Composable
private fun TransactionRow(transaction: com.adsearn.mobile.data.TransactionResponse) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(transaction.transaction_type.replace('_', ' ').replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.Medium)
                Text(transaction.transaction_id, style = MaterialTheme.typography.labelSmall)
                Text("${transaction.status} · ${formatDate(transaction.created_at)}", style = MaterialTheme.typography.bodySmall)
            }
            Text(transaction.amount, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun WithdrawalRow(withdrawal: WithdrawalResponse) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(withdrawal.withdrawal_id, fontWeight = FontWeight.Medium)
                AssistChip(onClick = {}, label = { Text(withdrawal.status) })
            }
            Text("${withdrawal.amount} · ${withdrawal.payment_method}")
            Text(formatDate(withdrawal.created_at), style = MaterialTheme.typography.bodySmall)
            withdrawal.payment_reference?.let { Text("Payment reference: $it", style = MaterialTheme.typography.bodySmall) }
        }
    }
}

@Composable
private fun ActionRow(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(17.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Medium)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Rounded.ChevronRight, contentDescription = null)
        }
    }
}

private fun nationalPhone(phone: String, iso: String?): String {
    if (iso.isNullOrBlank()) return phone
    return try {
        PhoneNumberUtil.getInstance().parse(phone, iso).let {
            PhoneNumberUtil.getInstance().getNationalSignificantNumber(it)
        }
    } catch (_: com.google.i18n.phonenumbers.NumberParseException) {
        phone
    }
}

private fun formatMoney(amount: BigDecimal, currencyCode: String): String {
    val formatter = NumberFormat.getCurrencyInstance(Locale.US)
    formatter.currency = Currency.getInstance(currencyCode)
    return formatter.format(amount)
}

private fun formatDate(value: String): String = value.replace('T', ' ').take(16)
