"""Find the application modules and their targetSdk without running Gradle."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexer import strip_comments

_NOISE = {"libs", "versions", "get", "toint", "toint()", "rootproject", "project", "ext", "extra", "property", "findproperty",
          "getproperty", "versionname", "integer", "parseint", "valueof", "int", "string", "tostring", "toi", "the"}
_TARGET = re.compile(r"""\btargetSdk(?:Version)?\b\s*(?:=|\(|\s)\s*(?P<expr>[^\n;}]+)""")
_TARGET_DSL = re.compile(r"""\btargetSdk\s*\{\s*version\s*=\s*release\(\s*([^)\s,]+)""")
_APP_PLUGIN = re.compile(r"""[\w.\-]*android\.application|libs\.plugins\.[\w.]*application|androidApplication|android-application""", re.I)


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass
class Module:
    dir: str  # repo-relative, "" for the root project
    build_file: str
    is_app: bool
    target: int | None = None
    target_line: int | None = None
    expr: str | None = None
    note: str | None = None
    floor_kind: str = "phone"
    sources: list[str] = field(default_factory=list)


def collect_constants(files: dict[str, str]) -> dict[str, int]:
    """name -> integer from gradle.properties, version catalogs, ext/extra blocks and Kotlin constants."""
    consts: dict[str, int] = {}

    def put(k: str, v: str) -> None:
        if re.fullmatch(r"\d{1,3}", v.strip().strip('"\'')):
            consts.setdefault(norm(k), int(v.strip().strip('"\'')))

    for path, text in files.items():
        base = path.rsplit("/", 1)[-1]
        if base == "gradle.properties":
            for line in text.splitlines():
                m = re.match(r"\s*([\w.\-]+)\s*[=:]\s*(\S+)", line)
                if m and not line.lstrip().startswith("#"):
                    put(m.group(1), m.group(2))
        elif base.endswith(".toml"):
            in_versions = False
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("["):
                    in_versions = s == "[versions]"
                elif in_versions:
                    m = re.match(r'([\w.\-]+)\s*=\s*"?(\d+)"?\s*(#.*)?$', s)
                    if m:
                        put(m.group(1), m.group(2))
        elif base.endswith((".gradle", ".gradle.kts", ".kt", ".kts")):
            code = strip_comments(text)
            for m in re.finditer(r"""(?:\bext(?:ra)?\s*(?:\.|\[\s*["'])|\bset\s*\(\s*["']|\bconst\s+val\s+|\bval\s+|\bdef\s+|\bext\s*\{[^}]*?)(\w+)["']?\s*\]?\s*(?:=|,)\s*(\d{2,3})\b""", code):
                put(m.group(1), m.group(2))
            for m in re.finditer(r"""^\s*(\w*[Ss]dk\w*)\s*=\s*(\d{2,3})\s*$""", code, re.M):
                put(m.group(1), m.group(2))
    return consts


def resolve(expr: str, consts: dict[str, int]) -> tuple[int | None, str]:
    e = expr.strip().rstrip(",").strip()
    m = re.fullmatch(r"""["']?(\d{1,3})["']?(?:\.toInt\(\))?\)?""", e)
    if m:
        return int(m.group(1)), "literal"
    tokens = [t for t in re.findall(r"[A-Za-z_]\w*", e) if t.lower() not in _NOISE]
    quoted = re.findall(r"""["'](\w[\w.\-]*)["']""", e)
    suffixes = ["".join(tokens[i:]) for i in range(len(tokens))]
    for cand in [*quoted, *suffixes, *(reversed(tokens))]:
        if cand and norm(cand) in consts:
            return consts[norm(cand)], f"via {cand}"
    return None, "unresolved"


def _declares_app(code: str) -> bool:
    """True when the file applies an application plugin (a root-project `apply false` does not count)."""
    for line in code.splitlines():
        if _APP_PLUGIN.search(line) and not re.search(r"apply\s*(?:\(\s*)?false", line):
            return True
    return False


_CONV_TARGET = re.compile(r"""\btargetSdk(?:Version)?(?:\s*=|\s*\(|[ \t]+(?=[\w"']))\s*([^;{}]{1,160})""")
_PLUGIN_DIRS = ("build-logic", "buildSrc", "build-plugin")


def _is_plugin_source(path: str) -> bool:
    """build-logic / buildSrc / build-plugin directories configure plugins; their build files are not apps."""
    return any(seg in _PLUGIN_DIRS for seg in path.split("/")[:-1])


def _expr_head(expr: str) -> str:
    """The expression after `targetSdk =`: up to the end of the statement, joined over line breaks when the value starts on the next line."""
    lines = [ln.strip() for ln in expr.splitlines()]
    out = lines[0] if lines and lines[0] else ""
    for ln in lines[1:3]:
        if out and not out.endswith((".", "(", "?", ":")) and not ln.startswith((".", "?", ":")):
            break
        out += ln
    return out


def _values(path: str, text: str, consts: dict[str, int]) -> list[int]:
    vals = []
    for m in _CONV_TARGET.finditer(strip_comments(text)):
        v, _ = resolve(_expr_head(m.group(1)), consts)
        if v is not None:
            vals.append(v)
    return vals


def _applied_plugins(code: str) -> tuple[set[str], set[str]]:
    """(plugin ids written as strings, normalised alias tails such as 'androidapplication')."""
    ids = set(re.findall(r"""\bid\s*\(?\s*["']([\w.\-]+)["']""", code))
    tails: set[str] = set()
    for m in re.finditer(r"""libs\.plugins\.([\w.]+)""", code):
        parts = [p for p in m.group(1).split(".") if p not in ("get", "id", "pluginid")]
        for n in (2, 3):
            if len(parts) >= n:
                tails.add(norm("".join(parts[-n:])))
    return ids, tails


def convention_target(files: dict[str, str], consts: dict[str, int], module_code: str = "", module_path: str = "") -> tuple[int | None, str]:
    """Heuristics for a targetSdk that is not in the module's own build file, from most to least specific.

    1. a precompiled script plugin whose file name is the plugin id the module applies (`thunderbird.app.android.gradle.kts`);
    2. a plugin class whose name contains the applied plugin alias (`libs.plugins.x.android.application` -> AndroidApplicationConventionPlugin);
    3. any plugin source (build-logic / buildSrc / build-plugin) when they all agree on one value;
    4. shared scripts at the repository root (`common.gradle`, a root `subprojects {}` block) when they agree.
    A result is only returned when the chosen group agrees on exactly one value."""
    ids, tails = _applied_plugins(module_code)
    plugin_files = {p: t for p, t in files.items() if _is_plugin_source(p) and p.endswith((".kt", ".kts", ".gradle"))}

    def pick(group: dict[str, str], why: str) -> tuple[int | None, str]:
        found: dict[int, str] = {}
        for p, t in sorted(group.items()):
            for v in _values(p, t, consts):
                found.setdefault(v, p)
        if len(found) == 1:
            (v, p), = found.items()
            return v, f"via {why} {p} (heuristic)"
        return None, ""

    by_id = {p: t for p, t in plugin_files.items() if re.sub(r"\.gradle(\.kts)?$", "", p.rsplit("/", 1)[-1]) in ids}
    by_alias = {p: t for p, t in plugin_files.items() if tails and any(tl in norm(p.rsplit("/", 1)[-1]) for tl in tails)}
    def shared_script(p: str) -> bool:
        name = p.rsplit("/", 1)[-1]
        if p == module_path or _is_plugin_source(p) or not name.endswith((".gradle", ".gradle.kts")) or name.startswith("settings."):
            return False
        depth = p.count("/")
        return depth == 0 or (depth == 1 and name not in ("build.gradle", "build.gradle.kts"))

    roots = {p: t for p, t in files.items() if shared_script(p)}
    for group, why in ((by_id, "precompiled script plugin"), (by_alias, "convention plugin"), (plugin_files, "build-logic"), (roots, "shared script")):
        if group:
            v, note = pick(group, why)
            if v is not None:
                return v, note
    return None, "unresolved"


def find_modules(files: dict[str, str]) -> list[Module]:
    consts = collect_constants(files)
    mods: list[Module] = []
    for path, text in sorted(files.items()):
        base = path.rsplit("/", 1)[-1]
        if base not in ("build.gradle", "build.gradle.kts"):
            continue
        d = path.rsplit("/", 1)[0] if "/" in path else ""
        code = strip_comments(text)
        is_app = _declares_app(code) and not _is_plugin_source(path)
        mod = Module(dir=d, build_file=path, is_app=is_app)
        if is_app:
            dsl = _TARGET_DSL.search(code)
            if dsl:
                val, how = resolve(dsl.group(1), consts)
                mod.target, mod.note = val, (how if val is None else f"{how} (targetSdk {{ version = release(..) }})")
                mod.expr, mod.target_line = f"release({dsl.group(1)})", code.count("\n", 0, dsl.start()) + 1
            else:
                found: list[tuple[int, int, str]] = []
                for m in _TARGET.finditer(code):
                    line = code.count("\n", 0, m.start()) + 1
                    val, how = resolve(m.group("expr"), consts)
                    if val is not None:
                        found.append((val, line, how))
                    elif mod.target_line is None:
                        mod.expr, mod.target_line, mod.note = m.group("expr").strip(), line, how
                if found:
                    val, line, how = min(found)
                    mod.target, mod.target_line, mod.note = val, line, how
                    mod.expr = None
                    others = sorted({v for v, _, _ in found})
                    if len(others) > 1:
                        mod.note = f"{how}; values differ in this file ({', '.join(map(str, others))}), the lowest is used"
        if is_app and mod.target is None:
            v, how = convention_target(files, consts, code, path)
            if v is not None:
                mod.target, mod.note = v, how
        mods.append(mod)
    return [m for m in mods if m.is_app]
