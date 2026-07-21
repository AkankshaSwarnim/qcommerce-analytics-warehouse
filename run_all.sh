#!/usr/bin/env bash
# Rebuild everything from nothing. ~90 seconds on a laptop, no cloud account.
#
# The order is the argument: generate -> land -> model -> test -> analyse ->
# score -> check the docs. Every stage fails loudly rather than warning, because
# a warning in a pipeline is a thing nobody reads twice.
set -euo pipefail

echo "== 1/8  generate synthetic source systems ==";  python3 src/generate_data.py
echo "== 2/8  land into warehouse raw schema ==";     python3 src/load_raw.py
echo "== 3/8  build + test the warehouse (dbt) ==";   (cd dbt && DBT_PROFILES_DIR=. dbt build)
echo "== 4/8  analyse (blind to answer key) ==";      python3 src/analysis.py
echo "== 5/8  score against ground truth ==";         python3 src/validate.py
echo "== 6/8  render docs from results ==";           python3 src/render_docs.py
echo "== 7/8  build dashboard + simulator ==";        python3 src/build_dashboard.py && python3 src/build_simulator.py
echo "== 8/8  verify docs match results ==";          python3 src/check_docs.py
echo
echo "All green."
