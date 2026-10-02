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
    for cand in [*quoted, "".join(tokens), *(reversed(tokens))]:
        if cand and norm(cand) in consts:
            return consts[norm(cand)], f"via {cand}"
    return None, "unresolved"


def _declares_app(code: str) -> bool:
    """True when the file applies an application plugin (a root-project `apply false` does not count)."""
    for line in code.splitlines():
        if _APP_PLUGIN.search(line) and not re.search(r"apply\s*(?:\(\s*)?false", line):
            return True
    return False


def _is_plugin_source(path: str) -> bool:
    """build-logic / buildSrc build files configure convention plugins; they are not apps themselves."""
    return any(seg in ("build-logic", "buildSrc") for seg in path.split("/")[:-1])


_CONV_TARGET = re.compile(r"""\btargetSdk(?:Version)?\s*(?:=|\()\s*([\w.]+)""")


def convention_target(files: dict[str, str], consts: dict[str, int]) -> tuple[int | None, str]:
    """Heuristic: a single targetSdk value set inside build-logic/buildSrc sources."""
    found: dict[int, str] = {}
    for path, text in sorted(files.items()):
        if not _is_plugin_source(path) or not path.endswith((".kt", ".kts", ".gradle")):
            continue
        for m in _CONV_TARGET.finditer(strip_comments(text)):
            val, _ = resolve(m.group(1), consts)
            if val is not None:
                found.setdefault(val, path)
    if len(found) == 1:
        (v, path), = found.items()
        return v, f"via convention plugin {path} (heuristic)"
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
            for m in ([] if dsl else _TARGET.finditer(code)):
                line = code.count("\n", 0, m.start()) + 1
                val, how = resolve(m.group("expr"), consts)
                mod.expr, mod.target_line = m.group("expr").strip(), line
                if val is not None:
                    mod.target, mod.note = val, how
                    break
                mod.note = how
        if is_app and mod.target is None:
            v, how = convention_target(files, consts)
            if v is not None:
                mod.target, mod.note = v, how
        mods.append(mod)
    return [m for m in mods if m.is_app]
