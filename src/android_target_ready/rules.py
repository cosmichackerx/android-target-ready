"""Rule table. Every rule cites the page of the Android documentation it comes from."""
from __future__ import annotations

from dataclasses import dataclass

A16 = "https://developer.android.com/about/versions/16/behavior-changes-16"
A17 = "https://developer.android.com/about/versions/17/behavior-changes-17"
PLAY = "https://support.google.com/googleplay/android-developer/answer/11926878"


@dataclass(frozen=True)
class Rule:
    id: str
    since: int  # targetSdk level from which the behaviour applies
    severity: str  # error | warning | info
    summary: str
    url: str
    #: severity once the app targets `escalate_at` or higher (the temporary opt-out disappears, ...)
    escalate_at: int | None = None
    escalate_to: str | None = None


RULES: dict[str, Rule] = {r.id: r for r in [
    Rule("play-target-floor", 36, "error",
         "targetSdk is below what Google Play requires for new apps and updates (36 since 2026-08-31; Wear OS 35, Android TV/XR 34).", PLAY),
    Rule("target-unresolved", 0, "info",
         "The targetSdk of an application module could not be determined statically (computed in a build script?).", PLAY),
    # --- Android 16 / API 36 ---
    Rule("edge-to-edge-opt-out", 36, "error",
         "windowOptOutEdgeToEdgeEnforcement=true: disabled on Android 16 devices once the app targets 36.", A16),
    Rule("back-pressed-override", 36, "warning",
         "onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback.", A16),
    Rule("back-keycode", 36, "warning",
         "KeyEvent.KEYCODE_BACK is not dispatched on Android 16 devices once the app targets 36. Use OnBackPressedCallback.", A16),
    Rule("back-opt-out", 36, "info",
         "android:enableOnBackInvokedCallback=\"false\" is the documented temporary opt-out from predictive back.", A16),
    Rule("elegant-text-height", 36, "warning",
         "elegantTextHeight is ignored once the app targets 36 (the UI-font APIs are discontinued).", A16),
    Rule("fixed-rate-scheduling", 36, "info",
         "scheduleAtFixedRate: at most one missed execution runs when the app returns to a valid lifecycle (target 36).", A16),
    Rule("body-sensors-permission", 36, "warning",
         "BODY_SENSORS / BODY_SENSORS_BACKGROUND are replaced by android.permissions.health.* permissions for apps targeting 36.", A16),
    Rule("fixed-orientation", 36, "warning",
         "android:screenOrientation with a portrait/landscape value is ignored on screens >= sw600dp (target 36; no opt-out at 37).", A16,
         escalate_at=37, escalate_to="error"),
    Rule("set-requested-orientation", 36, "warning",
         "setRequestedOrientation()/requestedOrientation with a portrait/landscape value is ignored on screens >= sw600dp (target 36; no opt-out at 37).", A16,
         escalate_at=37, escalate_to="error"),
    Rule("non-resizeable", 36, "warning",
         "android:resizeableActivity=\"false\" has no effect on screens >= sw600dp (target 36; no opt-out at 37).", A16,
         escalate_at=37, escalate_to="error"),
    Rule("aspect-ratio-limit", 36, "warning",
         "android:minAspectRatio / maxAspectRatio have no effect on screens >= sw600dp (target 36; no opt-out at 37).", A16,
         escalate_at=37, escalate_to="error"),
    Rule("large-screen-opt-out", 36, "info",
         "PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY is the temporary opt-out; it does not apply when targeting 37.", A16,
         escalate_at=37, escalate_to="error"),
    # --- Android 17 / API 37 ---
    Rule("local-network-permission", 37, "warning",
         "Local network access (NsdManager, multicast, mDNS/SSDP) needs the ACCESS_LOCAL_NETWORK runtime permission when targeting 37.", A17),
    Rule("bal-legacy-mode", 37, "warning",
         "MODE_BACKGROUND_ACTIVITY_START_ALLOWED is being replaced by granular modes such as MODE_BACKGROUND_ACTIVITY_START_ALLOW_IF_VISIBLE.", A17),
    Rule("content-capture-disable", 37, "warning",
         "setContentCaptureEnabled(false) no longer disables Content Capture when targeting 37; use FLAG_SECURE.", A17),
    Rule("native-load-writable", 37, "info",
         "Files loaded with System.load() must be read-only when targeting 37, otherwise UnsatisfiedLinkError.", A17),
    Rule("static-final-reflection", 37, "warning",
         "Modifying static final fields through reflection throws IllegalAccessException when targeting 37.", A17),
    Rule("message-queue-reflection", 37, "warning",
         "android.os.MessageQueue has a new lock-free implementation when targeting 37; reflection on its private members may break.", A17),
    Rule("contacts-pii-columns", 37, "warning",
         "ACCOUNT_NAME / ACCOUNT_TYPE / ACCOUNT_TYPE_AND_DATA_SET are removed from the ContactsContract.Data view when targeting 37; read them from RawContacts.", A17),
    Rule("rfcomm-read", 37, "info",
         "RFCOMM BluetoothSocket InputStream.read() returns -1 on close when targeting 37; loops that only catch IOException may not terminate.", A17),
    Rule("remoteviews-bitmap", 37, "info",
         "Bitmaps/Icons in a RemoteViews parcel are capped at 1.5 x screen width x height x 4 bytes when targeting 37; exceeding it crashes the process.", A17),
    Rule("sms-otp-delay", 37, "info",
         "Standard OTP SMS messages reach most apps only after three hours when targeting 37 (SMS Retriever / User Consent are exempt).", A17),
]}
