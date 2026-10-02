#!/usr/bin/env python3
"""Shallow-clone the repositories in repos.txt and run android-target-ready on each.

    python scripts/corpus/run.py --work /tmp/atr-corpus [--jobs 4]
    python scripts/corpus/stats.py /tmp/atr-corpus/out

Clones are public, depth 1, no credentials. Output: <work>/out/<owner>__<repo>.json
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "src")


def one(repo: str, work: str) -> str:
    name = repo.replace("/", "__")
    dest = os.path.join(work, "clones", name)
    if not os.path.isdir(dest):
        r = subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{repo}.git", dest],
                           capture_output=True, text=True, timeout=300, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode:
            return f"clone failed: {repo}"
    out = os.path.join(work, "out", name + ".json")
    with open(out, "w", encoding="utf-8") as fh:
        subprocess.run([sys.executable, "-m", "android_target_ready", dest, "-f", "json", "--fail-on", "never"],
                       stdout=fh, env={**os.environ, "PYTHONPATH": SRC}, timeout=300)
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--repos", default=os.path.join(HERE, "repos.txt"))
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.work, "clones"), exist_ok=True)
    os.makedirs(os.path.join(a.work, "out"), exist_ok=True)
    repos = [l.strip() for l in open(a.repos) if l.strip() and not l.startswith("#")]
    with ThreadPoolExecutor(a.jobs) as ex:
        for msg in ex.map(lambda r: one(r, a.work), repos):
            if msg:
                print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
