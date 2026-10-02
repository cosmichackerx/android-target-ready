plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.needswork"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.example.needswork"
        minSdk = 26
        targetSdk = 35
    }
}
