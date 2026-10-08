package com.adsearn.mobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF4F46E5),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE9E8FF),
    onPrimaryContainer = Color(0xFF211B7A),
    secondary = Color(0xFF17805D),
    onSecondary = Color.White,
    background = Color(0xFFF6F7FB),
    surface = Color.White,
    onSurface = Color(0xFF191B24),
    error = Color(0xFFB3261E),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB9B5FF),
    onPrimary = Color(0xFF27217F),
    primaryContainer = Color(0xFF3C348F),
    secondary = Color(0xFF6BD4A8),
    background = Color(0xFF101116),
    surface = Color(0xFF1A1B23),
    onSurface = Color(0xFFE6E2EC),
    error = Color(0xFFFFB4AB),
)

@Composable
fun AdsEarnTheme(theme: String, content: @Composable () -> Unit) {
    val dark = when (theme) {
        "Light" -> false
        "Dark" -> true
        else -> isSystemInDarkTheme()
    }
    MaterialTheme(
        colorScheme = if (dark) DarkColors else LightColors,
        content = content,
    )
}
