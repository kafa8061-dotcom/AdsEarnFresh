import java.util.Properties
import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use(::load)
}
val configuredApiUrl = providers.gradleProperty("API_BASE_URL")
    .orElse(localProperties.getProperty("API_BASE_URL") ?: "")
    .get()
val configuredIntegrityCloudProjectNumber = providers.gradleProperty("PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER")
    .orElse(localProperties.getProperty("PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER") ?: "")
    .get()
if (gradle.startParameter.taskNames.any { it.contains("production", ignoreCase = true) }) {
    val apiUri = runCatching { URI(configuredApiUrl) }.getOrNull()
    val apiHost = apiUri?.host?.lowercase()?.removePrefix("[")?.removeSuffix("]")?.removeSuffix(".")
    val localHost = apiHost == null ||
        apiHost == "localhost" ||
        apiHost.endsWith(".localhost") ||
        apiHost.endsWith(".local") ||
        apiHost.endsWith(".internal") ||
        apiHost.endsWith(".invalid") ||
        apiHost.endsWith(".test") ||
        apiHost.endsWith(".example") ||
        apiHost == "0.0.0.0" ||
        apiHost == "::1" ||
        apiHost.startsWith("127.") ||
        apiHost.startsWith("10.") ||
        apiHost.startsWith("192.168.") ||
        apiHost.startsWith("169.254.") ||
        (apiHost.contains(":") && (apiHost.startsWith("fc") || apiHost.startsWith("fd"))) ||
        apiHost.startsWith("fe80:") ||
        apiHost == "example.com" ||
        apiHost == "example.net" ||
        apiHost == "example.org" ||
        apiHost.endsWith(".example.com") ||
        apiHost.endsWith(".example.net") ||
        apiHost.endsWith(".example.org") ||
        Regex("""^172\.(1[6-9]|2[0-9]|3[01])\.""").containsMatchIn(apiHost)
    require(
        apiUri?.scheme == "https" &&
            !localHost &&
            configuredApiUrl.endsWith("/") &&
            apiUri.rawQuery == null &&
            apiUri.rawFragment == null &&
            apiUri.rawUserInfo == null,
    ) {
        "A real HTTPS API_BASE_URL is required for production variants; configure android/local.properties."
    }
    require(configuredIntegrityCloudProjectNumber.toLongOrNull()?.let { it > 0 } == true) {
        "PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER is required for production variants; configure android/local.properties."
    }
}

android {
    namespace = "com.adsearn.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.adsearn.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "API_BASE_URL", "\"${(configuredApiUrl.ifBlank { "https://api.example.invalid/" }).replace("\"", "\\\"")}\"")
        buildConfigField("String", "SUPPORT_EMAIL", "\"adsearn13@gmail.com\"")
        buildConfigField("long", "PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER", "${configuredIntegrityCloudProjectNumber.toLongOrNull() ?: 0L}L")
    }

    flavorDimensions += "environment"
    productFlavors {
        create("development") {
            dimension = "environment"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            resValue("string", "app_name", "AdsEarn (Development)")
            manifestPlaceholders["admobAppId"] = "ca-app-pub-3940256099942544~3347511713"
            buildConfigField("String", "REWARDED_AD_UNIT_ID", "\"ca-app-pub-3940256099942544/5224354917\"")
            buildConfigField("boolean", "IS_PRODUCTION", "false")
        }
        create("production") {
            dimension = "environment"
            manifestPlaceholders["admobAppId"] = "ca-app-pub-4973946737213196~3854510671"
            buildConfigField("String", "REWARDED_AD_UNIT_ID", "\"ca-app-pub-4973946737213196/2667340525\"")
            buildConfigField("boolean", "IS_PRODUCTION", "true")
            buildConfigField("String", "API_BASE_URL", "\"${(configuredApiUrl.ifBlank { "https://api.example.invalid/" }).replace("\"", "\\\"")}\"")
            buildConfigField("long", "PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER", "${configuredIntegrityCloudProjectNumber.toLongOrNull() ?: 0L}L")
        }
    }

    buildTypes {
        debug {
            isDebuggable = true
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.05.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("com.google.android.gms:play-services-ads:24.3.0")
    implementation("com.google.android.play:integrity:1.4.0")
    implementation("com.google.android.ump:user-messaging-platform:3.2.0")
    implementation("com.googlecode.libphonenumber:libphonenumber:8.13.55")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.13.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
