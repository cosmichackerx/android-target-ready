# android-target-ready

[![CI](https://github.com/cosmichackerx/android-target-ready/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmichackerx/android-target-ready/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cosmichackerx/android-target-ready?sort=semver)](https://github.com/cosmichackerx/android-target-ready/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Is your Android app ready for `targetSdk` 36 and 37?** A fast static scanner and GitHub Action that finds the code, manifest
entries and resources affected by the **Android 16 (API 36)** and **Android 17 (API 37)** behavior changes: edge-to-edge
enforcement, **predictive back** (`onBackPressed`, `KEYCODE_BACK`), **large-screen orientation and resizability** restrictions,
the new **local network permission**, background-activity-launch modes and more. It also checks the **Google Play target API
level requirement** (36 for phones since 2026-08-31, with Wear OS / TV / Automotive floors).

* Works on Kotlin, Java, Gradle (Groovy and Kotlin DSL), version catalogs, manifests and resource XML.
* **No Gradle run, no SDK, no dependencies**: Python 3.9+ standard library only. A big repository scans in seconds.
* Output as text, Markdown, JSON, GitHub annotations or **SARIF** (code scanning).
* Every rule links to the official Android documentation page that describes the change.
* Honest about its limits: see [Limitations](#limitations) and [docs/precision.md](docs/precision.md).

## Install and run

    pip install git+https://github.com/cosmichackerx/android-target-ready
    android-target-ready path/to/your/project

or without installing: `python -m android_target_ready .` from a checkout (`PYTHONPATH=src`).

## Example output

Real output on [TeamNewPipe/NewPipe](https://github.com/TeamNewPipe/NewPipe) (a shallow clone on 2026-10-03; this is a scan of public code, not a statement about the project):

```
app/build.gradle.kts
     47  error   play-target-floor          (API 36)  Application module `app` targets 35; Google Play requires 36 or higher for phone app updates since 2026-08-31 (extension requests to 2026-11-01).
         > release(NEWPIPE_VERSION_SDK_TARGET)

app/src/main/java/org/schabi/newpipe/error/ReCaptchaActivity.java
    130  warning back-pressed-override      (API 36)  onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback.
         > public void onBackPressed() {

app/src/main/java/org/schabi/newpipe/local/subscription/dialog/FeedGroupDialog.kt
    122  warning back-pressed-override      (API 36)  onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback.
         > override fun onBackPressed() {

app/src/main/java/org/schabi/newpipe/settings/SettingsActivity.java
    140  warning back-pressed-override      (API 36)  onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback.
         > public void onBackPressed() {

app/src/main/java/org/schabi/newpipe/util/FilePickerActivityHelper.java
     48  warning back-pressed-override      (API 36)  onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback.
         > public void onBackPressed() {

app/src/main/res/values-v35/styles.xml
      6  error   edge-to-edge-opt-out       (API 36)  windowOptOutEdgeToEdgeEnforcement=true: disabled on Android 16 devices once the app targets 36.
         > <item name="android:windowOptOutEdgeToEdgeEnforcement">true</item>

931 source/manifest/resource file(s) scanned for target 37; application modules: app: targetSdk 35. 2 error, 4 warning, 0 info.
```

The `play-target-floor` error is the Play requirement for phone apps; `edge-to-edge-opt-out` is the documented temporary opt-out
that stops working once the app targets 36; the `onBackPressed` warnings are activities and dialogs that will not get the callback
on Android 16 devices once the app targets 36 (use `OnBackPressedCallback`). A small project that is ready:

```
No target 37 migration findings.

2 source/manifest/resource file(s) scanned for target 37; application modules: app: targetSdk 37. 0 error, 0 warning, 0 info.
```

## GitHub Action

```yaml
name: android-target-ready
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v7
      - uses: cosmichackerx/android-target-ready@v0.2.2
        with:
          target: "37"        # 36 or 37
          fail-on: error      # error | warning | never
```

Inputs: `path`, `target`, `fail-on`, `disable`, `ignore`, `include-tests`, `summary` (job summary Markdown), `sarif-file`
(write SARIF, then upload with `github/codeql-action/upload-sarif`). Findings appear as annotations on the pull request.

### PR mode and sticky comment

On a pull request you usually care about what the change *adds*, not the backlog. With `pr-mode` the Action (or `--base REF` on the command line) scans the base revision too and reports only findings that are new. Findings are matched by rule, file and the normalised source line, not the line number, so moving code around does not make old findings look new; a second copy of an existing line does count as new.

```yaml
name: android-target-ready
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write      # only for the sticky comment
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0        # the base branch must be in the clone
      - uses: cosmichackerx/android-target-ready@v0.2.2
        with:
          comment: "true"       # implies pr-mode; one comment, updated in place
          fail-on: error        # only NEW findings can fail the pull request
```

The comment is created on the first new finding, updated in place afterwards (marker `<!-- android-target-ready:sticky -->`), and rewritten to "No new findings." once they are fixed; a clean pull request that never had a comment gets none. Pull requests from forks have a read-only token, so the comment is skipped with a notice there (annotations and the job summary still work). Real comment from this repository's own CI (pull request #9):

> **android-target-ready**: 3 source/manifest/resource file(s) scanned for target 37; application modules: app: targetSdk 37. 0 error, 1 warning, 0 info.
> PR mode against `origin/main`: 1 new, 0 already present (not shown), 0 resolved.
> | warning | `back-pressed-override` | 36 | `app/src/main/java/Added.kt:2` | onBackPressed() is not called on Android 16 devices once the app targets 36 ... |

Extra inputs: `pr-mode`, `base` (default `origin/<base branch>`), `comment`, `github-token`.

## Command line

    android-target-ready [path] [--target 36|37] [-f text|markdown|json|github|sarif] [-o FILE]
                         [--fail-on error|warning|never] [--disable RULE] [--ignore GLOB]
                         [--include-tests] [--base REF] [--list-rules]

Exit code 1 when a finding at or above `--fail-on` exists (default `error`), 2 on usage errors.
Suppress a finding in code with a comment on the same or the previous line: `// android-target-ready: ignore back-keycode`
(`ignore all` silences every rule on that line). Test source sets are skipped unless `--include-tests`. Games
(`android:appCategory="game"`) are exempt from the large-screen rules, as the platform documents.

## Rules

Severity can be higher at 37 where a temporary opt-out disappears.

| Rule | API | Severity | What it means | Docs |
|---|---|---|---|---|
| `play-target-floor` | 36 | error | targetSdk is below what Google Play requires for new apps and updates (36 since 2026-08-31; Wear OS 35, Android TV/XR 34). | [docs](https://support.google.com/googleplay/android-developer/answer/11926878) |
| `target-unresolved` | - | info | The targetSdk of an application module could not be determined statically (computed in a build script?). | [docs](https://support.google.com/googleplay/android-developer/answer/11926878) |
| `edge-to-edge-opt-out` | 36 | error | windowOptOutEdgeToEdgeEnforcement=true: disabled on Android 16 devices once the app targets 36. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `back-pressed-override` | 36 | warning | onBackPressed() is not called on Android 16 devices once the app targets 36 (predictive back is on by default). Use OnBackPressedCallback. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `back-keycode` | 36 | warning | KeyEvent.KEYCODE_BACK is not dispatched on Android 16 devices once the app targets 36. Use OnBackPressedCallback. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `back-opt-out` | 36 | info | android:enableOnBackInvokedCallback="false" is the documented temporary opt-out from predictive back. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `elegant-text-height` | 36 | warning | elegantTextHeight is ignored once the app targets 36 (the UI-font APIs are discontinued). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `fixed-rate-scheduling` | 36 | info | scheduleAtFixedRate: at most one missed execution runs when the app returns to a valid lifecycle (target 36). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `body-sensors-permission` | 36 | warning | BODY_SENSORS / BODY_SENSORS_BACKGROUND are replaced by android.permissions.health.* permissions for apps targeting 36. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `fixed-orientation` | 36 | warning → error at 37 | android:screenOrientation with a portrait/landscape value is ignored on screens >= sw600dp (target 36; no opt-out at 37). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `set-requested-orientation` | 36 | warning → error at 37 | setRequestedOrientation()/requestedOrientation with a portrait/landscape value is ignored on screens >= sw600dp (target 36; no opt-out at 37). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `non-resizeable` | 36 | warning → error at 37 | android:resizeableActivity="false" has no effect on screens >= sw600dp (target 36; no opt-out at 37). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `aspect-ratio-limit` | 36 | warning → error at 37 | android:minAspectRatio / maxAspectRatio have no effect on screens >= sw600dp (target 36; no opt-out at 37). | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `large-screen-opt-out` | 36 | info → error at 37 | PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY is the temporary opt-out; it does not apply when targeting 37. | [docs](https://developer.android.com/about/versions/16/behavior-changes-16) |
| `local-network-permission` | 37 | warning | Local network access (NsdManager, multicast, mDNS/SSDP) needs the ACCESS_LOCAL_NETWORK runtime permission when targeting 37. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `bal-legacy-mode` | 37 | warning | MODE_BACKGROUND_ACTIVITY_START_ALLOWED is being replaced by granular modes such as MODE_BACKGROUND_ACTIVITY_START_ALLOW_IF_VISIBLE. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `content-capture-disable` | 37 | warning | setContentCaptureEnabled(false) no longer disables Content Capture when targeting 37; use FLAG_SECURE. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `native-load-writable` | 37 | info | Files loaded with System.load() must be read-only when targeting 37, otherwise UnsatisfiedLinkError. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `static-final-reflection` | 37 | warning | Modifying static final fields through reflection throws IllegalAccessException when targeting 37. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `message-queue-reflection` | 37 | warning | android.os.MessageQueue has a new lock-free implementation when targeting 37; reflection on its private members may break. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `contacts-pii-columns` | 37 | warning | ACCOUNT_NAME / ACCOUNT_TYPE / ACCOUNT_TYPE_AND_DATA_SET are removed from the ContactsContract.Data view when targeting 37; read them from RawContacts. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `rfcomm-read` | 37 | info | RFCOMM BluetoothSocket InputStream.read() returns -1 on close when targeting 37; loops that only catch IOException may not terminate. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `remoteviews-bitmap` | 37 | info | Bitmaps/Icons in a RemoteViews parcel are capped at 1.5 x screen width x height x 4 bytes when targeting 37; exceeding it crashes the process. | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |
| `sms-otp-delay` | 37 | info | Standard OTP SMS messages reach most apps only after three hours when targeting 37 (SMS Retriever / User Consent are exempt). | [docs](https://developer.android.com/about/versions/17/behavior-changes-17) |

How `targetSdk` is found: literals, `libs.versions.toml`, `gradle.properties`, `ext`/`extra`, Kotlin `const val`,
AGP 9 `targetSdk { version = release(..) }`, and, when the module's own build file does not say, heuristics in this order: a precompiled script plugin named like the plugin id the module applies, a convention plugin class whose name matches the applied alias, all of `build-logic`/`buildSrc`/`build-plugin` when they agree on one value, and shared root scripts (`common.gradle`, `subprojects {}`) when they agree. Several values in one file (product flavors) report the lowest. If it cannot be determined
you get an `info` finding (`target-unresolved`) instead of a guess.

## How it relates to other tools

* **Android Lint** knows the project model, runs on the compiled sources and is authoritative; it covers some of these changes
  (for example edge-to-edge and API-level checks) when you actually raise `targetSdk`. android-target-ready is for the question
  *before* you raise it: "what will this cost?", across a repository, in seconds, without building.
* **Google's `check_elf_alignment.sh` and other 16 KB page-size checkers** look at native libraries; this tool does not.
* **Play-policy preflight tools** (for example GPC Preflight) work on a built app bundle and manifest; in a search on 2026-10-02 I found none that scans source for these behaviour changes. That is a search result, not a guarantee.

## Limitations

* Pattern based, line by line. No type resolution (the sibling [android-target-lint](https://github.com/cosmichackerx/android-target-lint) resolves types; on 52 shared repositories the two agreed on 71 % of the combined findings of six overlapping rules, see its [comparison](https://github.com/cosmichackerx/android-target-lint/blob/main/docs/corpus-comparison.md)): an `onBackPressed()` is only counted in files that extend a class called `*Activity` or `*Dialog`; a class hierarchy through a differently named base class is missed.
* Does not run Gradle, so targetSdk set by custom plugins, product flavors or `-P` flags can be unresolved or wrong.
* Not every Android 16/17 change is detectable statically; only the rules above exist. Recall is not measured.
* Measured on 100 public repos with a 40-finding hand-check (97.5 % after fixes, 82.5 % before): see [docs/precision.md](docs/precision.md). That is a sample read by the author, not a benchmark.
* Rules reflect the official documentation as fetched on 2026-10-02; Android 17 details can still change.

## Development

    pip install -e . pytest && pytest -q

CI runs the tests on Ubuntu, Windows and macOS (Python 3.9, 3.11, 3.13), builds the wheel/sdist and self-tests the Action.
See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md) and [SECURITY.md](SECURITY.md).

## Related tools

Small, independent tools by the same author, for build and CI hygiene and for migrations with a deadline. Each works on its own; none requires another.

**Gradle and Android migrations**

* [gradle-version-catalog-lint](https://github.com/cosmichackerx/gradle-version-catalog-lint): Lints `libs.versions.toml`: unused libraries, plugins and versions, dynamic or SNAPSHOT versions, hard-coded dependencies.
* [gradle10-ready](https://github.com/cosmichackerx/gradle10-ready): Static scan of Gradle build scripts for what Gradle 10 removes (space assignment, multi-string dependencies, Kotlin DSL delegates). `--fix`, PR mode.
* [agp9-ready](https://github.com/cosmichackerx/agp9-ready): Static scan of Gradle files for what Android Gradle Plugin 9 and 10 break (built-in Kotlin, legacy variant API, opt-outs), including `buildSrc`. `--fix`, PR mode.
* [android-target-lint](https://github.com/cosmichackerx/android-target-lint): The same targetSdk migration checks as real Android Lint rules (a lint jar with type resolution).

**CI and repository hygiene**

* [node24-ready](https://github.com/cosmichackerx/node24-ready): Finds GitHub Actions still on the removed Node 20 runtime, also inside composite actions and reusable workflows, and the smallest node24 upgrade.
* [dependabot-gaps](https://github.com/cosmichackerx/dependabot-gaps): Finds manifests your `dependabot.yml` does not cover, and dead or overlapping entries.
* [sha256-ready](https://github.com/cosmichackerx/sha256-ready): Finds code that assumes 40-character Git hashes before Git 3.0 makes SHA-256 repositories the default.
* [agent-context-diff](https://github.com/cosmichackerx/agent-context-diff): Diffs `AGENTS.md`, `CLAUDE.md`, Cursor rules and MCP configs between git refs (new servers, widened permissions, hidden Unicode).

## License

MIT
