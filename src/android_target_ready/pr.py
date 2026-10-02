"""PR mode: report only the findings a change introduces, by scanning the base revision too."""
from __future__ import annotations

import collections
import io
import os
import re
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass

from .scan import Finding, Result, scan


class BaseError(Exception):
    pass


@dataclass
class PrInfo:
    base: str
    new: int
    existing: int
    resolved: int


def finding_key(f: Finding) -> tuple[str, str, str]:
    """Identity of a finding across revisions: rule, file and the (whitespace-normalised) source line, not the line number."""
    return (f.rule, f.file, re.sub(r"\s+", " ", f.snippet).strip())


def diff_results(head: Result, base: Result, base_name: str) -> Result:
    """`head` reduced to the findings that are new compared with `base`. Duplicates are counted, so a second copy of a known line is new."""
    seen = collections.Counter(finding_key(f) for f in base.findings)
    new: list[Finding] = []
    existing = 0
    for f in head.findings:
        k = finding_key(f)
        if seen[k] > 0:
            seen[k] -= 1
            existing += 1
        else:
            new.append(f)
    resolved = sum(seen.values())
    out = Result(findings=new, modules=head.modules, files_scanned=head.files_scanned, target=head.target)
    out.pr = PrInfo(base=base_name, new=len(new), existing=existing, resolved=resolved)
    return out


def _git(args: list[str], cwd: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if p.returncode != 0:
        raise BaseError(p.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} failed")
    return p.stdout


def extract_base(path: str, ref: str, dest: str) -> None:
    """Export the tree of `ref` for the scanned directory (a sub-directory of the repository works) into `dest`."""
    top = _git(["rev-parse", "--show-toplevel"], path).decode().strip()
    prefix = _git(["rev-parse", "--show-prefix"], path).decode().strip()
    spec = f"{ref}:{prefix}" if prefix else ref
    try:
        data = _git(["archive", "--format=tar", spec], top)
    except BaseError as e:
        raise BaseError(f"cannot read '{ref}' (fetch it first, for example with fetch-depth: 0): {e}") from None
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        root = os.path.realpath(dest)
        for m in tf.getmembers():
            target = os.path.realpath(os.path.join(dest, m.name))
            if not (target == root or target.startswith(root + os.sep)) or m.issym() or m.islnk() or m.isdev():
                continue  # never write outside dest, never follow links
            tf.extract(m, dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def scan_pr(path: str, base_ref: str, **kw) -> Result:
    head = scan(path, **kw)
    with tempfile.TemporaryDirectory(prefix="atr-base-") as tmp:
        extract_base(path, base_ref, tmp)
        base = scan(tmp, **kw)
    return diff_results(head, base, base_ref)
