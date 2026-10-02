from __future__ import annotations

import json
import os
import subprocess
import sys

from android_target_ready.cli import main
from android_target_ready.lexer import strip_comments
from android_target_ready.report import render_github, render_json, render_markdown, render_sarif, render_text
from android_target_ready.rules import RULES
from android_target_ready.scan import scan
from helpers import APP_KTS, MANIFEST, project

FILES = {
    "app/build.gradle.kts": APP_KTS % "35",
    "app/src/main/AndroidManifest.xml": MANIFEST % '    <activity android:name=".A" android:screenOrientation="portrait" />\n',
    "app/src/main/java/Main.kt": "class Main : Activity() {\n  override fun onBackPressed() {}\n}\n",
}


def test_lexer_keeps_strings_and_line_numbers():
    src = 'val a = "// not a comment"\n// real comment KEYCODE_BACK\n/* block\n KEYCODE_BACK */ val b = 1\nval c = """a /* b */ c"""\n'
    out = strip_comments(src)
    assert out.count("\n") == src.count("\n")
    assert '"// not a comment"' in out and "KEYCODE_BACK" not in out and '"""a /* b */ c"""' in out


def test_renderers(tmp_path):
    r = scan(project(tmp_path, FILES), target=37)
    text = render_text(r)
    assert "app/src/main/java/Main.kt" in text and "back-pressed-override" in text and "(API 36)" in text
    md = render_markdown(r)
    assert md.startswith("## android-target-ready") and "| error |" in md and RULES["fixed-orientation"].url in md
    j = json.loads(render_json(r))
    assert j["target"] == 37 and j["modules"][0]["targetSdk"] == 35 and {f["rule"] for f in j["findings"]} >= {"play-target-floor", "fixed-orientation", "back-pressed-override"}
    gh = render_github(r)
    assert "::error file=app/build.gradle.kts,line=2,title=play-target-floor::" in gh
    sarif = json.loads(render_sarif(r))
    run = sarif["runs"][0]
    assert sarif["version"] == "2.1.0" and len(run["tool"]["driver"]["rules"]) == len(RULES)
    for res in run["results"]:
        assert run["tool"]["driver"]["rules"][res["ruleIndex"]]["id"] == res["ruleId"]
        assert res["locations"][0]["physicalLocation"]["region"]["startLine"] >= 1


def test_cli_exit_codes_and_options(tmp_path, capsys):
    d = project(tmp_path, FILES)
    assert main([d]) == 1  # play-target-floor / orientation errors
    assert main([d, "--fail-on", "never"]) == 0
    assert main([d, "--target", "36", "--disable", "play-target-floor", "--fail-on", "error"]) == 0  # only warnings left at 36
    assert main([d, "--target", "36", "--disable", "play-target-floor", "--fail-on", "warning"]) == 1
    assert main([d, "--disable", "nope"]) == 2
    out = tmp_path / "r.sarif"
    assert main([d, "-f", "sarif", "-o", str(out), "--fail-on", "never"]) == 0 and json.loads(out.read_text())["version"] == "2.1.0"
    assert main(["--list-rules"]) == 0 and "edge-to-edge-opt-out" in capsys.readouterr().out
    assert main([str(tmp_path / "nope")]) in (0, 2)


def test_ignore_glob_and_module_entry_point(tmp_path):
    d = project(tmp_path, FILES)
    r = scan(d, ignore=["app/src/main/java"])
    assert not any(f.rule == "back-pressed-override" for f in r.findings)
    p = subprocess.run([sys.executable, "-m", "android_target_ready", d, "--fail-on", "never"], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
    assert p.returncode == 0 and "play-target-floor" in p.stdout, p.stderr
