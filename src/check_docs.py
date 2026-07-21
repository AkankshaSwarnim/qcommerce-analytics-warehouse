"""
check_docs.py — fail if any rendered document is out of date.

WHAT THIS FILE USED TO BE, AND WHY IT WAS WRONG
-----------------------------------------------
Version 1 grepped every "+4.01 pp" out of the prose and asserted the value
appeared *somewhere* in reports/results.json.

It passed on stale documents. Twice.

reports/results.json holds several hundred floats, so "does this number appear
anywhere in this file" is a question almost nothing answers no. It matched a
stale headline of 94.08% against an unrelated basket-band figure and reported
no drift. The check could not fail, so it was not a check — it was a decoration
that stopped me looking.

Worse, it was the SAME class of error the project exists to demonstrate: a
metric that is technically correct, cheaply computed, and answers a different
question from the one being asked. The item-fill-rate mistake, one layer up, in
my own tooling.

WHAT IT IS NOW
--------------
The documents are no longer hand-written. src/render_docs.py generates them from
results.json; templates own the words, the renderer owns the figures.

So the honest check is byte equality: re-render into memory and diff against
what is on disk. There is no tolerance, no regex, no heuristic, and nothing to
tune. Either the committed doc is what the current results produce, or it is not.

This is the same move as `reporting_tz` in dbt_project.yml: define the value in
one place and the whole class of bug stops existing, rather than being policed
by a test that might be wrong in the same direction as the code.

RUN
    python src/check_docs.py       (exit 1 if any doc is stale)
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_docs import fields, RESULTS, TEMPLATES  # noqa: E402


def main() -> int:
    if not RESULTS.exists():
        print("reports/results.json missing — run src/analysis.py first.")
        return 1
    f = fields(json.loads(RESULTS.read_text()))

    stale = []
    for tmpl in sorted(TEMPLATES.glob("*.md.tmpl")):
        out = (Path("README.md") if tmpl.name == "README.md.tmpl"
               else Path("docs") / tmpl.name.replace(".tmpl", ""))
        expected = tmpl.read_text().format(**f)
        actual = out.read_text() if out.exists() else ""
        if expected != actual:
            stale.append(out)
            diff = list(difflib.unified_diff(
                actual.splitlines(), expected.splitlines(),
                fromfile=f"{out} (on disk)", tofile=f"{out} (from current results)",
                lineterm="", n=1))
            print("\n".join(diff[:24]))
            if len(diff) > 24:
                print(f"   ... {len(diff) - 24} more diff lines")
        else:
            print(f"  up to date: {out}")

    if stale:
        print(f"\n{len(stale)} document(s) STALE. Run: python src/render_docs.py")
        return 1
    print("\nall documents match the current results")
    return 0


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).resolve().parents[1])
    sys.exit(main())
