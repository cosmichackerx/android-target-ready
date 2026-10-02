#!/usr/bin/env python3
"""Summarise <work>/out/*.json: modules, target distribution, findings per rule. Optional --sample N prints N random findings with context."""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import random


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.out, "*.json")))
    rules, repos_with, targets = collections.Counter(), collections.Counter(), collections.Counter()
    mods = withfind = appr = 0
    rows = []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        appr += bool(d["modules"])
        for m in d["modules"]:
            mods += 1
            targets[str(m["targetSdk"])] += 1
        seen = set()
        for x in d["findings"]:
            rules[x["rule"]] += 1
            seen.add(x["rule"])
            rows.append((os.path.basename(f)[:-5], x))
        for r in seen:
            repos_with[r] += 1
        withfind += bool(d["findings"])
    print(f"repos scanned {len(files)}, with an application module {appr}, modules {mods}, repos with findings {withfind}")
    print("targetSdk of modules:", dict(sorted(targets.items())))
    for r, c in rules.most_common():
        print(f"{r:28s} {c:5d} findings in {repos_with[r]:3d} repos")
    if a.sample:
        random.seed(a.seed)
        pool = [r for r in rows if r[1]["rule"] not in ("target-unresolved", "play-target-floor")]
        random.shuffle(pool)
        for repo, x in pool[: a.sample]:
            print(f"\n{x['rule']}  {repo}/{x['file']}:{x['line']}\n    {x['snippet']}")


if __name__ == "__main__":
    main()
