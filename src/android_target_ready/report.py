"""Renderers: text, markdown, json, github annotations, sarif."""
from __future__ import annotations

import json

from . import __version__
from .rules import RULES
from .scan import Finding, Result

ORDER = {"error": 0, "warning": 1, "info": 2}


def counts(r: Result) -> dict[str, int]:
    c = {"error": 0, "warning": 0, "info": 0}
    for f in r.findings:
        c[f.severity] += 1
    return c


def _modules_line(r: Result) -> str:
    if not r.modules:
        return "no application module found (no `com.android.application` build file)"
    return "; ".join(f"{m.dir or '.'}: targetSdk {m.target if m.target is not None else '?'}" for m in r.modules)


def summary_line(r: Result) -> str:
    c = counts(r)
    return (f"{r.files_scanned} source/manifest/resource file(s) scanned for target {r.target}; application modules: {_modules_line(r)}. "
            f"{c['error']} error, {c['warning']} warning, {c['info']} info.")


def render_text(r: Result) -> str:
    out: list[str] = []
    if not r.findings:
        out.append(f"No target {r.target} migration findings.")
    last = None
    for f in sorted(r.findings, key=lambda f: (f.file, f.line)):
        if f.file != last:
            out.append(f"\n{f.file}")
            last = f.file
        out.append(f"  {f.line:>5}  {f.severity:<7} {f.rule:<26} (API {f.since or '-'})  {f.message}")
        if f.snippet:
            out.append(f"         > {f.snippet}")
    out.append("")
    out.append(summary_line(r))
    return "\n".join(out).lstrip("\n") + "\n"


def render_markdown(r: Result) -> str:
    out = ["## android-target-ready", "", summary_line(r), ""]
    if r.findings:
        out += ["| Severity | Rule | API | Where | Message |", "|---|---|---|---|---|"]
        for f in sorted(r.findings, key=lambda f: (ORDER[f.severity], f.file, f.line)):
            out.append(f"| {f.severity} | [`{f.rule}`]({f.url}) | {f.since or '-'} | `{f.file}:{f.line}` | {f.message.replace('|', chr(92) + '|')} |")
    else:
        out.append("No findings.")
    return "\n".join(out) + "\n"


def render_json(r: Result) -> str:
    return json.dumps({
        "tool": "android-target-ready", "version": __version__, "target": r.target, "filesScanned": r.files_scanned,
        "modules": [{"dir": m.dir, "buildFile": m.build_file, "targetSdk": m.target, "formFactor": m.floor_kind} for m in r.modules],
        "summary": counts(r),
        "findings": [{"rule": f.rule, "severity": f.severity, "file": f.file, "line": f.line, "since": f.since, "message": f.message, "snippet": f.snippet, "docs": f.url} for f in r.findings],
    }, indent=2) + "\n"


def render_github(r: Result) -> str:
    def esc(s: str) -> str:
        return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    lvl = {"error": "error", "warning": "warning", "info": "notice"}
    return "".join(f"::{lvl[f.severity]} file={f.file},line={f.line},title={f.rule}::{esc(f.message)}\n" for f in r.findings)


def render_sarif(r: Result) -> str:
    level = {"error": "error", "warning": "warning", "info": "note"}
    ids = list(RULES)
    rules = [{"id": i, "name": i, "shortDescription": {"text": RULES[i].summary}, "helpUri": RULES[i].url,
              "defaultConfiguration": {"level": level[RULES[i].severity]}} for i in ids]
    results = [{"ruleId": f.rule, "ruleIndex": ids.index(f.rule), "level": level[f.severity], "message": {"text": f.message},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": f.file, "uriBaseId": "%SRCROOT%"}, "region": {"startLine": max(1, f.line)}}}]}
               for f in r.findings]
    return json.dumps({"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
                       "runs": [{"tool": {"driver": {"name": "android-target-ready", "version": __version__,
                                                    "informationUri": "https://github.com/cosmichackerx/android-target-ready", "rules": rules}}, "results": results}]}, indent=2) + "\n"


def meets_threshold(r: Result, fail_on: str) -> bool:
    if fail_on == "never":
        return False
    return any(f.severity == "error" or (fail_on == "warning" and f.severity == "warning") for f in r.findings)
