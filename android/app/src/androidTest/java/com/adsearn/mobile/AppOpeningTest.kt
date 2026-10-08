package com.adsearn.mobile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AppOpeningTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun openingShowsHomeInsteadOfAuthentication() {
        compose.waitUntil(5_000) {
            compose.onAllNodesWithText("Welcome to AdsEarn").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Welcome to AdsEarn").assertIsDisplayed()
    }
}
