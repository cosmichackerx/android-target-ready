from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from android_target_ready import comment
from android_target_ready.cli import main
from android_target_ready.pr import BaseError, scan_pr

APP = 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk = 37 } }\n'
MAIN_OLD = "class Main : AppCompatActivity() {\n  override fun onBackPressed() {}\n}\n"
MAIN_NEW = "// a new first line moves everything down\n// and another\nclass Main : AppCompatActivity() {\n  override fun onBackPressed() {}\n}\nclass Other : AppCompatActivity() {\n  override fun onBackPressed() {}\n}\n"


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def repo(tmp_path, sub=""):
    root = tmp_path / "r"
    app = root / sub if sub else root
    (app / "app/src/main/java").mkdir(parents=True)
    (app / "app/build.gradle.kts").write_text(APP)
    (app / "app/src/main/java/Main.kt").write_text(MAIN_OLD)
    root.mkdir(exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-q", "-b", "feature")
    return root, app


def test_only_new_findings_are_reported_and_line_moves_do_not_count(tmp_path):
    root, app = repo(tmp_path)
    (app / "app/src/main/java/Main.kt").write_text(MAIN_NEW)
    res = scan_pr(str(app), "main")
    assert (res.pr.new, res.pr.existing, res.pr.resolved) == (1, 1, 0)
    assert [(f.rule, f.line) for f in res.findings] == [("back-pressed-override", 7)]


def test_resolved_findings_are_counted_and_unchanged_pr_is_clean(tmp_path):
    root, app = repo(tmp_path)
    same = scan_pr(str(app), "main")
    assert (same.pr.new, same.pr.existing, same.pr.resolved) == (0, 1, 0)
    (app / "app/src/main/java/Main.kt").write_text("class Main : AppCompatActivity()\n")
    fixed = scan_pr(str(app), "main")
    assert (fixed.pr.new, fixed.pr.existing, fixed.pr.resolved) == (0, 0, 1)


def test_works_for_a_subdirectory_of_the_repository(tmp_path):
    root, app = repo(tmp_path, sub="android")
    (app / "app/src/main/java/Main.kt").write_text(MAIN_NEW)
    res = scan_pr(str(app), "main")
    assert res.pr.new == 1 and res.pr.existing == 1


def test_unknown_base_is_a_clear_error_and_cli_exit_codes(tmp_path, capsys):
    root, app = repo(tmp_path)
    with pytest.raises(BaseError, match="cannot read 'nope'"):
        scan_pr(str(app), "nope")
    assert main([str(app), "--base", "nope"]) == 2
    (app / "app/src/main/java/Main.kt").write_text(MAIN_NEW)
    capsys.readouterr()
    assert main([str(app), "--base", "main", "--fail-on", "warning", "-f", "json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["pr"] == {"base": "main", "new": 1, "existing": 1, "resolved": 0} and len(out["findings"]) == 1
    (app / "app/src/main/java/Main.kt").write_text(MAIN_OLD)
    assert main([str(app), "--base", "main", "--fail-on", "warning"]) == 0  # existing findings never fail a PR


class Fake(BaseHTTPRequestHandler):
    comments: list[dict] = []
    log: list[str] = []

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Fake.log.append("GET " + self.path)
        self._send(Fake.comments)

    def do_POST(self):
        Fake.log.append("POST " + self.path)
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        c = {"id": len(Fake.comments) + 1, "body": body["body"]}
        Fake.comments.append(c)
        self._send(c, 201)

    def do_PATCH(self):
        Fake.log.append("PATCH " + self.path)
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Fake.comments[0]["body"] = body["body"]
        self._send(Fake.comments[0])

    def log_message(self, *a):
        pass


def test_sticky_comment_created_once_then_updated(tmp_path, monkeypatch):
    Fake.comments, Fake.log = [], []
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api = f"http://127.0.0.1:{srv.server_port}"
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    body = tmp_path / "b.md"
    body.write_text("first")
    assert comment.main(["--body-file", str(body), "--repo", "o/r", "--pr", "3", "--api-url", api, "--clean"]) == 0
    assert Fake.comments == []  # clean and no earlier comment: stay quiet
    assert comment.main(["--body-file", str(body), "--repo", "o/r", "--pr", "3", "--api-url", api]) == 0
    body.write_text("second")
    assert comment.main(["--body-file", str(body), "--repo", "o/r", "--pr", "3", "--api-url", api]) == 0
    assert comment.main(["--body-file", str(body), "--repo", "o/r", "--pr", "3", "--api-url", api, "--clean"]) == 0
    srv.shutdown()
    assert len(Fake.comments) == 1 and Fake.comments[0]["body"].startswith(comment.MARKER) and "second" in Fake.comments[0]["body"]
    assert [l.split()[0] for l in Fake.log if not l.startswith("GET")] == ["POST", "PATCH"]


def test_comment_is_skipped_for_fork_pull_requests(tmp_path, monkeypatch, capsys):
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"pull_request": {"number": 5, "head": {"repo": {"full_name": "someone/fork"}}}}))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    body = tmp_path / "b.md"
    body.write_text("x")
    assert comment.main(["--body-file", str(body), "--repo", "o/r", "--api-url", "http://127.0.0.1:1"]) == 0
    assert "fork" in capsys.readouterr().err
