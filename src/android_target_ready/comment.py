"""Sticky pull request comment: one comment, found by a marker, updated in place.

    python -m android_target_ready.comment --body-file report.md --repo owner/name --pr 12

The token comes from GITHUB_TOKEN. Pull requests from forks get a read-only token: the comment is then skipped with a notice (exit 0).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MARKER = "<!-- android-target-ready:sticky -->"
UA = "android-target-ready"


def _call(api: str, token: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(api.rstrip("/") + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": UA,
                                          "X-GitHub-Api-Version": "2022-11-28", **({"Content-Type": "application/json"} if body is not None else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def find_existing(api: str, token: str, repo: str, pr: int) -> dict | None:
    page = 1
    while page <= 10:  # 1000 comments are enough; stay polite with the rate limit
        items = _call(api, token, "GET", f"/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}")
        for c in items:
            if MARKER in (c.get("body") or ""):
                return c
        if len(items) < 100:
            return None
        page += 1
    return None


def upsert(api: str, token: str, repo: str, pr: int, body: str, clean: bool) -> str:
    """Create or update the sticky comment. A clean report only updates an existing comment (no new noise)."""
    text = f"{MARKER}\n{body.strip()}\n"
    existing = find_existing(api, token, repo, pr)
    if existing:
        if (existing.get("body") or "") == text:
            return "unchanged"
        _call(api, token, "PATCH", f"/repos/{repo}/issues/comments/{existing['id']}", {"body": text})
        return "updated"
    if clean:
        return "skipped (nothing to report and no earlier comment)"
    _call(api, token, "POST", f"/repos/{repo}/issues/{pr}/comments", {"body": text})
    return "created"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="android-target-ready-comment")
    p.add_argument("--body-file", required=True)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    p.add_argument("--pr", type=int)
    p.add_argument("--clean", action="store_true", help="the report has no findings")
    p.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    a = p.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    pr = a.pr
    if pr is None and os.environ.get("GITHUB_EVENT_PATH"):
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            ev = json.load(f)
        pr = (ev.get("pull_request") or {}).get("number")
        head = ((ev.get("pull_request") or {}).get("head") or {}).get("repo") or {}
        if head.get("full_name") and a.repo and head["full_name"].lower() != a.repo.lower():
            print("android-target-ready: pull request from a fork (read-only token): sticky comment skipped", file=sys.stderr)
            return 0
    if not (token and a.repo and pr):
        print("android-target-ready: sticky comment needs GITHUB_TOKEN, --repo and a pull request number; skipped", file=sys.stderr)
        return 0
    with open(a.body_file, encoding="utf-8") as f:
        body = f.read()
    try:
        print(f"android-target-ready: sticky comment {upsert(a.api_url, token, a.repo, pr, body, a.clean)}")
    except urllib.error.HTTPError as e:
        # 403/404 on a read-only token is expected for some triggers; do not fail the build for a comment
        print(f"android-target-ready: sticky comment skipped: HTTP {e.code}", file=sys.stderr)
    except (urllib.error.URLError, OSError) as e:
        print(f"android-target-ready: sticky comment skipped: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
