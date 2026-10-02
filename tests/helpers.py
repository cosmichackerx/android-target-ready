from __future__ import annotations

import os

from android_target_ready.scan import scan


def project(tmp_path, files: dict[str, str]):
    for p, c in files.items():
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c, encoding="utf-8")
    return str(tmp_path)


def run(tmp_path, files, **kw):
    return scan(project(tmp_path, files), **kw)


def ids(res):
    return sorted(f"{f.rule}:{f.severity}" for f in res.findings)


APP_KTS = 'plugins { id("com.android.application") }\nandroid { defaultConfig { targetSdk = %s } }\n'
MANIFEST = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n  <application>\n%s  </application>\n</manifest>\n'
