from __future__ import annotations

from helpers import APP_KTS, MANIFEST, ids, run


def app(target="36", extra=None):
    d = {"app/build.gradle.kts": APP_KTS % target}
    d.update(extra or {})
    return d


def test_clean_project_has_no_findings(tmp_path):
    r = run(tmp_path, app("37", {"app/src/main/AndroidManifest.xml": MANIFEST % '    <activity android:name=".Main" />\n'}))
    assert ids(r) == []
    assert r.modules[0].target == 37


def test_edge_to_edge_opt_out_only_when_true(tmp_path):
    r = run(tmp_path, app(extra={
        "app/src/main/res/values/themes.xml": '<resources>\n<style name="A">\n<item name="android:windowOptOutEdgeToEdgeEnforcement">true</item>\n</style>\n<style name="B">\n<item name="android:windowOptOutEdgeToEdgeEnforcement">false</item>\n</style>\n</resources>\n'}))
    assert ids(r) == ["edge-to-edge-opt-out:error"]
    assert r.findings[0].line == 3


def test_predictive_back_rules_kotlin_and_java_comments_ignored(tmp_path):
    r = run(tmp_path, app(extra={
        "app/src/main/java/a/Main.kt": 'class Main : Activity() {\n  override fun onBackPressed() { super.onBackPressed() }\n  // override fun onBackPressed() {}\n  /* KEYCODE_BACK in a comment */\n  fun k(e: KeyEvent) = e.keyCode == KeyEvent.KEYCODE_BACK\n}\n',
        "app/src/main/java/a/Old.java": "public class Old extends Activity {\n  @Override\n  public void onBackPressed() { }\n  void x() { dispatcher.onBackPressed(); }\n}\n"}))
    assert ids(r) == ["back-keycode:warning", "back-pressed-override:warning", "back-pressed-override:warning"]
    assert sorted((f.file.split("/")[-1], f.line) for f in r.findings if f.rule == "back-pressed-override") == [("Main.kt", 2), ("Old.java", 3)]


def test_large_screen_rules_escalate_at_37(tmp_path):
    files = app(extra={"app/src/main/AndroidManifest.xml": MANIFEST % (
        '    <activity android:name=".A" android:screenOrientation="portrait" android:resizeableActivity="false" android:maxAspectRatio="1.86" />\n'
        '    <activity android:name=".B" android:screenOrientation="unspecified" />\n'
        '    <property android:name="android.window.PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY" android:value="true" />\n')})
    r36 = run(tmp_path / "a", files, target=36)
    assert ids(r36) == ["aspect-ratio-limit:warning", "fixed-orientation:warning", "large-screen-opt-out:info", "non-resizeable:warning"]
    r37 = run(tmp_path / "b", files, target=37)
    assert set(f.severity for f in r37.findings) == {"error"} and len(r37.findings) == 4


def test_games_are_exempt_from_the_large_screen_rules(tmp_path):
    r = run(tmp_path, app(extra={"app/src/main/AndroidManifest.xml": '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:appCategory="game">\n<activity android:screenOrientation="landscape"/>\n</application></manifest>\n'}))
    assert ids(r) == []


def test_set_requested_orientation_only_for_restricting_values(tmp_path):
    r = run(tmp_path, app(extra={"app/src/main/java/A.kt": "fun f(a: Activity) {\n a.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT\n a.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED)\n a.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE)\n}\n"}), target=36)
    assert ids(r) == ["set-requested-orientation:warning"] * 2


def test_back_opt_out_and_permissions(tmp_path):
    r = run(tmp_path, app(extra={"app/src/main/AndroidManifest.xml": MANIFEST.replace("<application>", '<uses-permission android:name="android.permission.BODY_SENSORS"/>\n<uses-permission android:name="android.permission.RECEIVE_SMS"/>\n<application android:enableOnBackInvokedCallback="false">') % ""}))
    assert ids(r) == ["back-opt-out:info", "body-sensors-permission:warning", "sms-otp-delay:info"]


def test_api37_rules_and_target_filter(tmp_path):
    src = {"app/src/main/java/N.kt": (
        "val m = getSystemService(NsdManager::class.java)\n"
        "val o = ActivityOptions.makeBasic().setPendingIntentBackgroundActivityStartMode(ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED)\n"
        "fun c(m: ContentCaptureManager) = m.setContentCaptureEnabled(false)\n"
        "fun l() = System.load(\"/data/x.so\")\n"
        "val f = Field::class.java.getDeclaredField(\"modifiers\")\n"
        "val q = MessageQueue::class.java.getDeclaredField(\"mMessages\")\n"
        "val col = ContactsContract.Data.ACCOUNT_NAME\n"
        "val s = adapter.createRfcommSocketToServiceRecord(uuid)\n"
        "fun r(v: RemoteViews) = v.setImageViewBitmap(1, bmp)\n"
        "val t = ses.scheduleAtFixedRate(task, 0, 1, SECONDS)\n")}
    r37 = run(tmp_path / "a", app("36", src), target=37)
    assert ids(r37) == sorted(["local-network-permission:warning", "bal-legacy-mode:warning", "content-capture-disable:warning", "native-load-writable:info",
                              "static-final-reflection:warning", "message-queue-reflection:warning", "contacts-pii-columns:warning", "rfcomm-read:info",
                              "remoteviews-bitmap:info", "fixed-rate-scheduling:info"])
    r36 = run(tmp_path / "b", app("36", src), target=36)
    assert ids(r36) == ["fixed-rate-scheduling:info"]


def test_local_network_rule_silent_when_permission_declared(tmp_path):
    r = run(tmp_path, app(extra={
        "app/src/main/java/N.kt": "val m = getSystemService(NsdManager::class.java)\n",
        "app/src/main/AndroidManifest.xml": MANIFEST.replace("<application>", '<uses-permission android:name="android.permission.ACCESS_LOCAL_NETWORK"/>\n<application>') % ""}))
    assert ids(r) == []


def test_inline_ignore_same_and_previous_line(tmp_path):
    r = run(tmp_path, app(extra={"app/src/main/java/A.kt": (
        "class A {\n"
        "  // android-target-ready: ignore back-pressed-override\n"
        "  override fun onBackPressed() {}\n"
        "  fun k(e: KeyEvent) = e.keyCode == KeyEvent.KEYCODE_BACK // android-target-ready: ignore\n"
        "  fun j(e: KeyEvent) = e.keyCode == KeyEvent.KEYCODE_BACK\n}\n")}))
    assert ids(r) == ["back-keycode:warning"] and r.findings[0].line == 5


def test_tests_are_skipped_unless_asked_and_disable_works(tmp_path):
    files = app(extra={"app/src/test/java/T.kt": "fun t(k: Int) = k == KeyEvent.KEYCODE_BACK\n", "app/src/main/java/M.kt": "fun m(k: Int) = k == KeyEvent.KEYCODE_BACK\n"})
    assert [f.file for f in run(tmp_path / "a", files).findings] == ["app/src/main/java/M.kt"]
    assert len(run(tmp_path / "b", files, include_tests=True).findings) == 2
    assert run(tmp_path / "c", files, disabled={"back-keycode"}).findings == []


def test_play_floor_and_form_factors(tmp_path):
    phone = run(tmp_path / "a", {"app/build.gradle.kts": APP_KTS % "35"})
    assert ids(phone) == ["play-target-floor:error"]
    assert "requires 36" in phone.findings[0].message
    wear = run(tmp_path / "b", {"app/build.gradle.kts": APP_KTS % "35", "app/src/main/AndroidManifest.xml": MANIFEST.replace("<application>", '<uses-feature android:name="android.hardware.type.watch"/>\n<application>') % ""})
    assert ids(wear) == []
    tv = run(tmp_path / "c", {"app/build.gradle.kts": APP_KTS % "33", "app/src/main/AndroidManifest.xml": MANIFEST.replace("<application>", '<uses-feature android:name="android.software.leanback"/>\n<application>') % ""})
    assert ids(tv) == ["play-target-floor:error"] and "requires 34" in tv.findings[0].message


def test_target_resolution_variants(tmp_path):
    toml = '[versions]\ntargetSdk = "36"\ncompile-sdk = "36"\n[libraries]\n'
    cases = {
        "groovy": ("app/build.gradle", "plugins { id 'com.android.application' }\nandroid { defaultConfig { targetSdkVersion 35 } }\n", {}),
        "catalog": ("app/build.gradle.kts", 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk = libs.versions.targetSdk.get().toInt() } }\n', {"gradle/libs.versions.toml": toml}),
        "props": ("app/build.gradle.kts", 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk = (project.property("TARGET_SDK") as String).toInt() } }\n', {"gradle.properties": "TARGET_SDK=35\n"}),
        "ext": ("app/build.gradle", "plugins { id 'com.android.application' }\nandroid { defaultConfig { targetSdkVersion rootProject.ext.targetSdkVersion } }\n", {"build.gradle": "ext {\n  targetSdkVersion = 34\n}\n"}),
        "alias": ("app/build.gradle.kts", 'plugins { alias(libs.plugins.android.application) }\nandroid { defaultConfig { targetSdk = 36 } }\n', {}),
    }
    want = {"groovy": 35, "catalog": 36, "props": 35, "ext": 34, "alias": 36}
    for name, (path, text, extra) in cases.items():
        r = run(tmp_path / name, {path: text, **extra})
        assert [m.target for m in r.modules] == [want[name]], name


def test_unresolved_and_library_modules(tmp_path):
    r = run(tmp_path, {"app/build.gradle.kts": 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk = computeTarget() } }\n',
                       "lib/build.gradle.kts": 'plugins { id("com.android.library") }\nandroid { defaultConfig { targetSdk = 30 } }\n'})
    assert ids(r) == ["target-unresolved:info"]
    assert [m.dir for m in r.modules] == ["app"]


def test_build_and_generated_dirs_are_skipped(tmp_path):
    r = run(tmp_path, app(extra={"app/build/generated/X.kt": "fun x(k: Int) = k == KeyEvent.KEYCODE_BACK\n"}))
    assert ids(r) == []


def test_local_network_flags_usage_not_the_import(tmp_path):
    r = run(tmp_path, app(extra={"app/src/main/java/N.kt": "import android.net.nsd.NsdManager\n\nfun f(c: Context) = c.getSystemService(NsdManager::class.java)\n"}))
    assert [f.line for f in r.findings] == [3]


def test_root_build_file_with_apply_false_is_not_an_app_module(tmp_path):
    res = run(tmp_path, {
        "build.gradle.kts": 'plugins { alias(libs.plugins.android.application) apply false\n id("com.android.application") version "9.0" apply false }\n',
        "app/build.gradle.kts": APP_KTS % "36",
    })
    assert [m.dir for m in res.modules] == ["app"]


def test_convention_plugin_target_is_used_when_unambiguous(tmp_path):
    res = run(tmp_path, {
        "app/build.gradle.kts": 'plugins { id("com.example.android.application") }\n',
        "build-logic/convention/src/main/kotlin/AppPlugin.kt": "class P { fun c() { extension.defaultConfig.targetSdk = 36 } }\n",
    })
    (m,) = res.modules
    assert m.target == 36 and "convention plugin" in m.note
    assert not any(f.rule == "target-unresolved" for f in res.findings)


def test_convention_plugin_with_two_values_stays_unresolved(tmp_path):
    res = run(tmp_path, {
        "app/build.gradle.kts": 'plugins { id("com.android.application") }\n',
        "build-logic/a.kt": "x.targetSdk = 35\n",
        "build-logic/b.kt": "x.targetSdk = 36\n",
    })
    assert res.modules[0].target is None


def test_agp9_target_sdk_block_dsl(tmp_path):
    res = run(tmp_path, {"app/build.gradle.kts": 'plugins { id("com.android.application") }\nandroid { defaultConfig {\n targetSdk {\n version = release(37)\n}\n} }\n'})
    assert res.modules[0].target == 37


def test_agp9_target_sdk_one_line(tmp_path):
    res = run(tmp_path, {"app/build.gradle.kts": 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk { version = release(36) } } }\n'})
    assert res.modules[0].target == 36


def test_imports_and_declarations_are_not_uses(tmp_path):
    res = run(tmp_path, {
        "app/build.gradle.kts": APP_KTS % "37",
        "app/src/main/java/A.kt": "import android.app.ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED\nfun f(v: View) { v.setContentCaptureEnabled(true) }\n",
        "app/src/main/java/B.java": "class B {\n  protected BluetoothSocket createRfcommSocketToServiceRecord(UUID u) { return null; }\n}\n",
    })
    assert ids(res) == []


def test_back_rules_skip_custom_methods_and_non_handling_mentions(tmp_path):
    res = run(tmp_path, app(extra={
        "app/src/main/java/a/Frag.kt": "open class F {\n  open fun onBackPressed() {}\n  override fun onBackPressed(): Boolean { return false }\n  fun go() { keyevent(KeyEvent.KEYCODE_BACK) }\n  fun n(k: Int) = k != KeyEvent.KEYCODE_BACK\n}\n"}))
    assert ids(res) == []


def test_on_back_pressed_needs_an_activity_or_dialog_subclass_and_device_tests_are_skipped(tmp_path):
    res = run(tmp_path, app(extra={
        "app/src/main/java/Scene.java": "class Scene extends PixelScene {\n  @Override\n  public void onBackPressed() {}\n}\n",
        "app/src/main/java/Act.java": "class Act extends AppCompatActivity {\n  @Override\n  public void onBackPressed() {}\n}\n",
        "app/src/androidDeviceTest/AndroidManifest.xml": MANIFEST % '    <activity android:name=".A" android:screenOrientation="portrait"/>\n',
    }))
    assert [(f.rule, f.file.split("/")[-1]) for f in res.findings] == [("back-pressed-override", "Act.java")]
