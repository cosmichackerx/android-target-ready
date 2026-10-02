# Precision: what was measured, and what was not

android-target-ready is a **static, regex-and-heuristic** scanner. A finding means "this construct is present and the
Android docs describe a behaviour change for it". It does **not** mean the app will break; Android Lint and a test run on
an Android 16/17 device stay authoritative.

## Corpus

100 public Android repositories (`scripts/corpus/repos.txt`): GitHub search for the `android` topic and Jetpack Compose
repos with ≥ 800-1500 stars, pushed after 2026-08-01, < 400 MB, shallow-cloned on 2026-10-02/03. Reproduce with

    python scripts/corpus/run.py --work /tmp/atr-corpus
    python scripts/corpus/stats.py /tmp/atr-corpus/out --sample 40

## Hand-check 1 (found real problems)

40 random findings (excluding `play-target-floor` and `target-unresolved`), each read in its source context:
33 were the described construct in app code; **7 were false positives** (82.5 %):

* 5 × `onBackPressed()` in a game engine's own `Scene`/`Window` classes (not an Activity),
* 1 × `NsdManager` in Robolectric's `@Implements` shadow,
* 1 × an `androidDeviceTest` manifest (test directory not recognised).

Also found by looking at the corpus as a whole: root `build.gradle(.kts)` files with `alias(libs.plugins.android.application) apply false`
were counted as application modules (221 modules, 116 with unresolved targetSdk instead of 145 and 29 today),
and AGP 9's `targetSdk { version = release(36) }` was not understood. All fixed, each with a regression test.

## Hand-check 2 (after the fixes, different random seed)

40 random findings: **39 were the described construct, 1 false positive** (97.5 %): `case KEYCODE_BACK:` in a terminal
emulator's key-to-escape-sequence table (not back handling). It is not filtered because a `switch` on `keyCode` in a real
Activity looks the same. A later full-corpus re-run added two more fixes found while writing the README example (NewPipe):
`targetSdk { version = release(CONST) }` with a constant, and `android.software.leanback` with `required="false"` no longer forces the TV floor.

## Caveats

* The sample is 40 of ~280 findings, read by the tool's author, after the rules had been tuned on the same corpus. Treat 97.5 % as an optimistic figure for this corpus, not a general precision.
* "Described construct" is judged against the text of the Android docs, not by running the app on Android 16/17.
* Recall is not measured at all. Rules only look at the patterns they were written for; Kotlin/Java is matched per line.
* Some hits are in vendored libraries or demo apps inside the repository (e.g. `leanback` copies); they are real hits in that repository's code.
* `target-unresolved` still appears for projects whose targetSdk is computed in custom build logic.

## Resolver check (v0.2.0)

Of the 143 application modules found in the corpus, 21 still have no targetSdk (29 before the resolver). The 6 modules that gained a value
(AntennaPod `common.gradle`, AppManager `versions.gradle`, komi-store and mihon version catalogs, two ShizukuPlus modules via a root `subprojects` block)
were each checked against the build files: all 6 are correct. The remaining 21 are mostly computed values (`config.build.targetSdkVersion`, `VersionCodes.*`, `compileSdk` aliases) and projects that hold the value in several unrelated build files.
