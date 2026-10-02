# Changelog

## 0.2.0 - 2026-10-03

* **PR mode (issue #1):** `--base REF` and the Action inputs `pr-mode`, `base`, `comment`, `github-token`; only new findings are reported and can fail the build; a sticky pull request comment (`android_target_ready.comment`) is created/updated in place and skipped for forks. CI exercises both on every pull request (Linux and Windows).
* **targetSdk resolver (issue #2):** precompiled script plugins matched by plugin id, convention plugin classes matched by alias, multi-line `findVersion(..)`/dotted catalog accessors, shared root scripts such as `common.gradle`, lowest value across product flavors. On the 100-repository corpus 6 more modules got a target (all 6 checked by hand), unresolved went from 29 to 21 of 143 modules; `build-plugin` directories are no longer mistaken for apps.
* Windows CI fix for the CLI test (empty environment).

## 0.1.0 - 2026-10-03

First release.

* 23 rules for what changes when an app moves its targetSdk to 36 (edge-to-edge opt-out, predictive back, large-screen orientation and resizability, `scheduleAtFixedRate`, `BODY_SENSORS`) and 37 (local network permission, background-activity-launch modes, content capture, `System.load`, static-final reflection, MessageQueue reflection, contacts columns, RFCOMM read, RemoteViews bitmaps, SMS OTP delay) plus the Google Play target-API floor with Wear OS / TV / Automotive floors.
* Reads the targetSdk without running Gradle: literals, version catalogs, `gradle.properties`, `ext`/`extra`, Kotlin consts, AGP 9 `targetSdk { version = release(..) }`, and a single value set in `build-logic`/`buildSrc` convention plugins.
* Text, Markdown, JSON, GitHub annotation and SARIF 2.1.0 output; `--fail-on`, `--target 36|37`, `--disable`, `--ignore`, `--include-tests`, inline `android-target-ready: ignore <rule>`.
* Composite GitHub Action (`action.yml`) with step summary and SARIF file.
* CI on Linux, Windows and macOS (Python 3.9 / 3.11 / 3.13), package build, action self-test.
* Corpus scripts (`scripts/corpus`) and a documented hand-check (`docs/precision.md`).
