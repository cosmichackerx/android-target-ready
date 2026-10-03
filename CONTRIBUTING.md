# Contributing

    python -m venv .venv && . .venv/bin/activate
    pip install -e . pytest
    pytest -q

* A new rule needs: an entry in `src/android_target_ready/rules.py` with a link to the official Android documentation that describes the change, a pattern in `scan.py`, and a test with one positive and one negative case.
* Every rule must stay quiet on comments, imports and declarations; add the false positive you found as a regression test.
* Run `python scripts/corpus/run.py --work /tmp/atr-corpus` before and after a rule change and look at the diff in `stats.py`.
* Keep the project dependency-free (standard library only) and compatible with Python 3.9.
* Releasing: bump the version and the README pins in a PR, merge when green, then run **Actions > Release gate** with the new tag (for example `v1.2.3`) *before* you create the tag. The same check runs again on the tag, and a weekly job (`claims-latest.yml`) fails when the README pins an older release than the newest tag.
