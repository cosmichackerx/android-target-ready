from __future__ import annotations

import argparse
import sys

from . import __version__
from .report import meets_threshold, render_github, render_json, render_markdown, render_sarif, render_text
from .rules import RULES
from .pr import BaseError, scan_pr
from .scan import scan

RENDER = {"text": render_text, "markdown": render_markdown, "json": render_json, "github": render_github, "sarif": render_sarif}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="android-target-ready", description="Static scan of an Android project for what changes when targetSdk moves to 36 and 37.")
    p.add_argument("path", nargs="?", default=".", help="project directory (default: .)")
    p.add_argument("--target", type=int, choices=(36, 37), default=37, help="report rules that apply up to this targetSdk (default: 37)")
    p.add_argument("-f", "--format", choices=sorted(RENDER), default="text")
    p.add_argument("-o", "--output", help="write the report to a file")
    p.add_argument("--fail-on", choices=("error", "warning", "never"), default="error", help="exit 1 on findings of this level or worse (default: error)")
    p.add_argument("--disable", action="append", default=[], metavar="RULE", help="turn a rule off (repeatable)")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="leave matching paths out (repeatable)")
    p.add_argument("--include-tests", action="store_true", help="also scan src/test and src/androidTest")
    p.add_argument("--base", metavar="REF", help="PR mode: scan this git ref too and report only the findings that are new (needs the ref in the local clone)")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--version", action="version", version=f"android-target-ready {__version__}")
    a = p.parse_args(argv)
    if a.list_rules:
        for r in RULES.values():
            print(f"{r.id:<26} API {r.since or '-':<3} {r.severity:<8} {r.summary}")
        return 0
    unknown = [d for d in a.disable if d not in RULES]
    if unknown:
        print(f"android-target-ready: unknown rule(s): {', '.join(unknown)} (see --list-rules)", file=sys.stderr)
        return 2
    try:
        kw = dict(target=a.target, disabled=set(a.disable), include_tests=a.include_tests, ignore=a.ignore)
        res = scan_pr(a.path, a.base, **kw) if a.base else scan(a.path, **kw)
    except (OSError, BaseError) as e:
        print(f"android-target-ready: {e}", file=sys.stderr)
        return 2
    text = RENDER[a.format](res)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 1 if meets_threshold(res, a.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
