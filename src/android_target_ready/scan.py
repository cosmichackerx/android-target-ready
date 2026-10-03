"""Walk a project, apply the rules, return findings."""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field

from .gradle import Module, find_modules
from .lexer import strip_comments
from .rules import PLAY, RULES, Rule

SKIP_DIRS = {".git", "build", ".gradle", "node_modules", ".idea", "out", "generated", ".svn", ".hg", "Pods", "DerivedData", ".dart_tool"}
TEST_DIR = re.compile(r"(^|/)src/(test|androidTest|testDebug|testRelease|androidTestDebug|sharedTest|commonTest|jvmTest|iosTest|desktopTest|androidDeviceTest|androidUnitTest|androidInstrumentedTest|androidHostTest)[^/]*/", re.I)
MAX_BYTES = 2_000_000

PORTRAIT_LANDSCAPE = r"(?:portrait|landscape|reversePortrait|reverseLandscape|sensorPortrait|sensorLandscape|userPortrait|userLandscape)"
ORIENT_CONST = r"SCREEN_ORIENTATION_(?:PORTRAIT|LANDSCAPE|REVERSE_PORTRAIT|REVERSE_LANDSCAPE|SENSOR_PORTRAIT|SENSOR_LANDSCAPE|USER_PORTRAIT|USER_LANDSCAPE)\b"

IGNORE_RE = re.compile(r"android-target-ready:\s*ignore\s*([\w\-, ]*)", re.I)


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    message: str
    snippet: str = ""

    @property
    def since(self) -> int:
        return RULES[self.rule].since

    @property
    def url(self) -> str:
        return RULES[self.rule].url


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    files_scanned: int = 0
    target: int = 37
    pr: object | None = None  # PrInfo when scanned in PR mode


# (rule, regex, kinds) -- kinds: "xml" manifest/resources, "code" Kotlin/Java, "manifest" AndroidManifest.xml only
LINE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("edge-to-edge-opt-out", re.compile(r"windowOptOutEdgeToEdgeEnforcement[\"']?(?:\s+[\w:.-]+\s*=\s*\"[^\"]*\")*\s*>\s*(?:true|@bool/\w+)", re.I), "xml"),
    ("back-opt-out", re.compile(r"android:enableOnBackInvokedCallback\s*=\s*[\"']false[\"']"), "manifest"),
    ("fixed-orientation", re.compile(rf"android:screenOrientation\s*=\s*[\"']{PORTRAIT_LANDSCAPE}[\"']"), "manifest"),
    ("non-resizeable", re.compile(r"android:resizeableActivity\s*=\s*[\"']false[\"']"), "manifest"),
    ("aspect-ratio-limit", re.compile(r"android:(?:min|max)AspectRatio\s*=|android\.max_aspect"), "manifest"),
    ("large-screen-opt-out", re.compile(r"PROPERTY_COMPAT_ALLOW_RESTRICTED_RESIZABILITY"), "manifest"),
    ("body-sensors-permission", re.compile(r"android\.permission\.BODY_SENSORS(?:_BACKGROUND)?[\"']"), "manifest"),
    ("sms-otp-delay", re.compile(r"android\.permission\.(?:RECEIVE_SMS|READ_SMS)[\"']"), "manifest"),
    ("elegant-text-height", re.compile(r"elegantTextHeight[\"']?\s*(?:=\s*[\"']false[\"']|>\s*false\b)"), "xml"),
    ("elegant-text-height", re.compile(r"(?:setElegantTextHeight\s*\(\s*false\s*\)|\bisElegantTextHeight\s*=\s*false\b)"), "code"),
    ("back-pressed-override", re.compile(r"\boverride\s+fun\s+onBackPressed\s*\(\s*\)\s*(?![:\s]*\w)|\b(?:public|protected)\s+void\s+onBackPressed\s*\(\s*\)"), "code"),
    ("back-keycode", re.compile(r"(?:==|\bcase)\s*(?:KeyEvent\.)?KEYCODE_BACK\b|\bKEYCODE_BACK\s*(?:==|->|:)"), "code"),
    ("fixed-rate-scheduling", re.compile(r"\.scheduleAtFixedRate\s*\("), "code"),
    ("set-requested-orientation", re.compile(rf"(?:setRequestedOrientation\s*\(|\brequestedOrientation\s*=(?!=))[^\n]*{ORIENT_CONST}"), "code"),
    ("bal-legacy-mode", re.compile(r"\bMODE_BACKGROUND_ACTIVITY_START_ALLOWED\b"), "code"),
    ("content-capture-disable", re.compile(r"\bsetContentCaptureEnabled\s*\(\s*false\b"), "code"),
    ("native-load-writable", re.compile(r"(?:\bSystem|\bRuntime\.getRuntime\(\))\.load\s*\("), "code"),
    ("static-final-reflection", re.compile(r"""getDeclaredField\s*\(\s*["'](?:modifiers|accessFlags)["']\s*\)"""), "code"),
    ("contacts-pii-columns", re.compile(r"\bContactsContract\.Data\.ACCOUNT_(?:NAME|TYPE_AND_DATA_SET|TYPE)\b"), "code"),
    ("remoteviews-bitmap", re.compile(r"\bsetImageViewBitmap\s*\(|\bsetBitmap\s*\(\s*R\.id|\bsetImageViewIcon\s*\([^)]*createWithBitmap"), "code"),
]
ACTIVITY_LIKE = re.compile(r"(?:\bextends|:)\s*[\w.]*(?:Activity|Dialog)\b")  # onBackPressed only matters on Activity/Dialog subclasses
IMPORT_LINE = re.compile(r"\s*import\s")
DECLARATION = re.compile(r"\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private)\s")  # method/field declarations, not calls
LOCAL_NET = re.compile(r"\bNsdManager\b|\bMulticastSocket\b|\bcreateMulticastLock\b|\bjavax\.jmdns\b|\bJmDNS\b")
RFCOMM = re.compile(r"\b(?:createRfcommSocketToServiceRecord|createInsecureRfcommSocketToServiceRecord|listenUsingRfcommWithServiceRecord|listenUsingInsecureRfcommWithServiceRecord)\b")
MQ_REFLECT = re.compile(r"""getDeclared(?:Field|Method)\s*\(\s*["'](m[A-Z]\w+|next|enqueueMessage|postSyncBarrier|removeSyncBarrier)["']""")
LOCAL_NET_PERM = re.compile(r"android\.permission\.ACCESS_LOCAL_NETWORK")
GAME = re.compile(r"""android:appCategory\s*=\s*["']game["']""")
LARGE_SCREEN_RULES = {"fixed-orientation", "non-resizeable", "aspect-ratio-limit", "large-screen-opt-out"}


def read(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def walk(root: str) -> list[str]:
    out: list[str] = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            out.append(os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/"))
    return sorted(out)


def _requires_feature(manifest: str, name: str) -> bool:
    """True for <uses-feature android:name=NAME/> that is not marked android:required="false" (a TV-optional phone app keeps the phone floor)."""
    for m in re.finditer(r"<uses-feature\b[^>]*>", manifest):
        tag = m.group(0)
        if name in tag and not re.search(r"""android:required\s*=\s*["']false["']""", tag):
            return True
    return False


def severity_for(rule: Rule, target: int) -> str:
    if rule.escalate_at is not None and target >= rule.escalate_at and rule.escalate_to:
        return rule.escalate_to
    return rule.severity


def _ignored(lines: list[str], idx: int, rule: str) -> bool:
    for j in (idx, idx - 1):
        if 0 <= j < len(lines):
            if j != idx and not lines[j].lstrip().startswith(("//", "/*", "*", "<!--", "#")):
                continue  # an ignore at the end of a code line only covers that line
            m = IGNORE_RE.search(lines[j])
            if m:
                ids = {x.strip().lower() for x in re.split(r"[,\s]+", m.group(1)) if x.strip()}
                if not ids or "all" in ids or rule in ids:
                    return True
    return False


def scan(root: str, target: int = 37, disabled: set[str] | None = None, include_tests: bool = False, ignore: list[str] | None = None) -> Result:
    disabled = disabled or set()
    ignore = ignore or []
    res = Result(target=target)
    all_files = [p for p in walk(root) if not any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, g + "/*") for g in ignore)]

    gradle_files = {p: t for p in all_files if p.rsplit("/", 1)[-1] in ("build.gradle", "build.gradle.kts", "gradle.properties", "settings.gradle", "settings.gradle.kts")
                    or p.endswith(".toml") or p.endswith((".gradle", ".gradle.kts")) or ("buildSrc" in p or "build-logic" in p) and p.endswith((".kt", ".kts", ".gradle"))
                    if (t := read(os.path.join(root, p))) is not None}
    res.modules = find_modules(gradle_files)

    texts: dict[str, str] = {}
    for p in all_files:
        is_code = p.endswith((".kt", ".java"))
        is_xml = p.endswith(".xml")
        if not (is_code or is_xml):
            continue
        if not include_tests and TEST_DIR.search(p):
            continue
        if is_xml and not (p.endswith("AndroidManifest.xml") or re.search(r"(^|/)res/[^/]+/[^/]+\.xml$", p)):
            continue
        t = read(os.path.join(root, p))
        if t is not None:
            texts[p] = t
    res.files_scanned = len(texts)

    manifests = {p: t for p, t in texts.items() if p.endswith("AndroidManifest.xml")}
    has_local_net_perm = any(LOCAL_NET_PERM.search(t) for t in manifests.values())

    def add(rule_id: str, path: str, line: int, lines: list[str], idx: int) -> None:
        if rule_id in disabled or RULES[rule_id].since > target or _ignored(lines, idx, rule_id):
            return
        rule = RULES[rule_id]
        res.findings.append(Finding(rule_id, severity_for(rule, target), path, line, rule.summary, lines[idx].strip()[:160]))

    for path, text in sorted(texts.items()):
        is_code = path.endswith((".kt", ".java"))
        is_manifest = path.endswith("AndroidManifest.xml")
        raw_lines = text.splitlines()
        if is_code:
            body = strip_comments(text)
        else:
            body = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
        lines = body.splitlines()
        game = is_manifest and bool(GAME.search(body))
        for rule_id, rx, kind in LINE_PATTERNS:
            if kind == "code" and not is_code:
                continue
            if kind == "manifest" and not is_manifest:
                continue
            if kind == "xml" and is_code:
                continue
            if game and rule_id in LARGE_SCREEN_RULES:
                continue  # documented exception: games (android:appCategory="game")
            for i, line in enumerate(lines):
                if is_code and IMPORT_LINE.match(line):
                    continue  # an import is not a use
                if rule_id == "back-pressed-override" and not ACTIVITY_LIKE.search(body):
                    break  # e.g. a game engine's own Scene/Window.onBackPressed
                if rx.search(line):
                    add(rule_id, path, i + 1, raw_lines, i)
        if is_code:
            if not has_local_net_perm:
                for i, line in enumerate(lines):
                    if LOCAL_NET.search(line) and not IMPORT_LINE.match(line) and not line.lstrip().startswith("@Implements"):
                        add("local-network-permission", path, i + 1, raw_lines, i)
                        break
            for i, line in enumerate(lines):
                if RFCOMM.search(line) and not DECLARATION.match(line):
                    add("rfcomm-read", path, i + 1, raw_lines, i)
                    break
            if "MessageQueue" in body:
                for i, line in enumerate(lines):
                    if MQ_REFLECT.search(line):
                        add("message-queue-reflection", path, i + 1, raw_lines, i)

    # application modules: Google Play floor
    for m in res.modules:
        mf = next((t for p, t in manifests.items() if p.startswith((m.dir + "/" if m.dir else "")) and p.endswith("src/main/AndroidManifest.xml")), "")
        if "android.hardware.type.watch" in mf:
            m.floor_kind = "wear"
        elif _requires_feature(mf, "android.software.leanback") or _requires_feature(mf, "android.hardware.type.television"):
            m.floor_kind = "tv"
        elif "android.hardware.type.automotive" in mf:
            m.floor_kind = "auto"
        floor = {"phone": 36, "wear": 35, "tv": 34, "auto": 35}[m.floor_kind]
        label = m.dir or "."
        if m.target is None and "target-unresolved" not in disabled:
            why = "not set in the module's build file (a convention plugin may set it)" if m.target_line is None else f"expression `{m.expr}` could not be resolved"
            res.findings.append(Finding("target-unresolved", "info", m.build_file, m.target_line or 1, f"Application module `{label}`: targetSdk {why}.", m.expr or ""))
        elif m.target is not None and m.target < floor and "play-target-floor" not in disabled:
            res.findings.append(Finding("play-target-floor", "error", m.build_file, m.target_line or 1,
                                        f"Application module `{label}` targets {m.target}; Google Play requires {floor} or higher for {m.floor_kind} app updates since 2026-08-31 (extension requests to 2026-11-01).", m.expr or ""))
    res.findings.sort(key=lambda f: (f.file, f.line, f.rule))
    return res
