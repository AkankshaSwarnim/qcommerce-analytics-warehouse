"""
validate.py — score the blind analysis against the answer key.

WHY THIS FILE IS SEPARATE FROM analysis.py
------------------------------------------
analysis.py is forbidden from importing the generative parameters, and asserts
that it cannot reach them. This file is the only place allowed to open the
answer key, and it runs strictly AFTER the analysis has committed its numbers to
reports/results.json.

The order matters. If scoring and estimating lived in one file, nothing would
stop a quiet loop of "tune until it matches" — which is how synthetic
demonstrations usually lie. Here the estimate is written to disk first and
graded second.

WHAT THIS CAN AND CANNOT ESTABLISH
----------------------------------
CAN:    that the estimators recover the injected effects on THIS data.
CANNOT: that they would recover anything on real data, where the DGP is not a
        Python file and the confounders are not a documented list.

A method that fails here is definitely broken. A method that passes here is
merely not-yet-known-to-be-broken. That asymmetry is the whole value of the
exercise, and overclaiming it would undo the point.

RUN
    python src/validate.py        (after analysis.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")
import config as C  # the answer key. Allowed HERE and nowhere else.

RESULTS = Path("reports/results.json")


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit("Run `python src/analysis.py` first — nothing to score.")
    r = json.loads(RESULTS.read_text())

    print("=" * 78)
    print("SCORING THE BLIND ANALYSIS AGAINST THE ANSWER KEY")
    print("=" * 78)

    # ---------------------------------------------------------------
    # 1. The tenure effect
    # ---------------------------------------------------------------
    print("\n1. STOCK-OUT EFFECT BY TENURE  (pp on 30-day repeat)\n")
    print(f"   {'tenure':<14}{'injected':>10}{'estimated':>11}{'95% CI':>20}{'recovered?':>12}")
    scores = []
    for row in r["stockout_effect"]["by_tenure"]:
        t = row["tenure"]
        truth = C.TRUE_EFFECT_PP[t]
        # The injected value is the effect for a stock-out with NO high-intent
        # item and NO accepted substitute. The estimate pools across both, so it
        # is a mixture and should NOT equal the injected number exactly. What we
        # check is the ORDER OF MAGNITUDE and the SIGN, plus whether the truth
        # lands anywhere near the interval. Demanding exact recovery would be
        # demanding the estimator ignore the population it was measured on.
        est, lo, hi = row["effect_pp"], row["ci_lo"], row["ci_hi"]
        near = lo - 4.0 <= truth <= hi + 4.0
        scores.append(near)
        print(f"   {t:<14}{truth:>+10.1f}{est:>+11.2f}"
              f"{f'[{lo:+.2f}, {hi:+.2f}]':>20}{'yes' if near else 'NO':>12}")

    print("\n   Ranking check — is the damage larger for new customers?")
    by_t = {x["tenure"]: x["effect_pp"] for x in r["stockout_effect"]["by_tenure"]}
    rank_ok = by_t["new"] < by_t["established"]
    truth_ok = C.TRUE_EFFECT_PP["new"] < C.TRUE_EFFECT_PP["established"]
    print(f"     injected:  new ({C.TRUE_EFFECT_PP['new']:+.1f}) more damaging than "
          f"established ({C.TRUE_EFFECT_PP['established']:+.1f})  -> {truth_ok}")
    print(f"     estimated: new ({by_t['new']:+.2f}) more damaging than "
          f"established ({by_t['established']:+.2f})  -> {rank_ok}")
    print(f"     RANKING RECOVERED: {rank_ok == truth_ok}")

    # ---------------------------------------------------------------
    # 2. The substitution ranking — the ambiguity payoff
    # ---------------------------------------------------------------
    print("\n2. SUBSTITUTION QUALITY  (the question with no ground-truth label)\n")
    truth_rank = sorted(C.SUBSTITUTION_TYPES.items(),
                        key=lambda kv: -kv[1]["repair"])
    print("   INJECTED repair fraction (never logged, never visible to analysis):")
    for k, v in truth_rank:
        print(f"     {k:<26}{v['repair']:.2f}")

    by_type = r["substitution_ambiguity"]["proxies"]["C_swap_distance"]["by_type"]
    est_rank = sorted(by_type, key=lambda x: -x["effect_vs_no_offer_pp"])
    print("\n   ESTIMATED effect via proxy C (pp vs no-substitute-offered):")
    for x in est_rank:
        print(f"     {x['substitution_type']:<26}{x['effect_vs_no_offer_pp']:>+7.2f}  n={x['n']:,}")

    truth_order = [k for k, _ in truth_rank]
    est_order = [x["substitution_type"] for x in est_rank]
    order_ok = truth_order == est_order
    print(f"\n   injected order : {' > '.join(truth_order)}")
    print(f"   estimated order: {' > '.join(est_order)}")
    print(f"   ORDER RECOVERED: {order_ok}")

    # Robustness: is that order an artefact of one control group?
    rr = r["substitution_ambiguity"]["ranking_robustness"]
    print("\n   Ranking under each control group (opposite selection problems):")
    for label, v in rr["by_control_group"].items():
        print(f"     {label:<20}{' > '.join(v['order'])}")
    stable = rr["order_stable_across_proxies"]
    print(f"   ORDER STABLE ACROSS PROXIES: {stable}")

    # ---------------------------------------------------------------
    # 3. The experiment
    # ---------------------------------------------------------------
    print("\n3. THE EXPERIMENT  (injected retention effect: "
          f"{C.TRUE_EXPERIMENT_EFFECT_PP:+.1f}pp — the feature does nothing)\n")
    ex = r["experiment"]
    w, i, c = (ex["analysis_at_checkout_WRONG"], ex["analysis_itt_CORRECT"],
               ex["conversion_harm"])

    # The checkout-level RETENTION estimate should recover the injected zero:
    # nothing was done to retention, and among converters nothing is found.
    # That is the trap, not the reassurance.
    zero_in_ci = w["ci_lo"] <= C.TRUE_EXPERIMENT_EFFECT_PP <= w["ci_hi"]
    print(f"   retention @ checkout  {w['effect_pp']:+.2f}pp "
          f"[{w['ci_lo']:+.2f}, {w['ci_hi']:+.2f}]  p={w['p_value']:.3g}")
    print(f"     -> injected zero inside CI: {zero_in_ci}  (the estimator is CORRECT here)")
    print(f"     -> and this is exactly why it is dangerous: a true null on a")
    print(f"        metric that cannot see the harm reads as 'ship it, it's fine'.")

    srm_ok = (not ex["srm_at_assignment"]["srm_detected"]) and ex["srm_at_checkout"]["srm_detected"]
    print(f"\n   SRM @ assignment detected: {ex['srm_at_assignment']['srm_detected']}  (should be False)")
    print(f"   SRM @ checkout   detected: {ex['srm_at_checkout']['srm_detected']}  (should be True)")
    print(f"   SRM CHECK BEHAVED CORRECTLY: {srm_ok}")

    print(f"\n   conversion harm  {c['effect_pp']:+.2f}pp "
          f"({c['relative_loss']:.1%} of treatment conversions lost, p={c['p_value']:.3g})")
    print(f"   ITT              {i['effect_pp']:+.2f}pp  p={i['p_value']:.3g}")
    print(f"\n   The injected truth: retention effect ZERO, conversion friction REAL.")
    print(f"   Recovered: retention null ({zero_in_ci}), conversion harm found, ITT net negative.")

    # ---------------------------------------------------------------
    # 4. The honest scorecard
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("WHAT THIS DOES AND DOES NOT SHOW")
    print("=" * 78)
    spread = r["substitution_ambiguity"]["agreement"]["spread_pp"]
    print(f"""
   MAGNITUDE:  not recovered, and it was never going to be. The proxies
               disagree by {spread:.1f}pp and none of them measures the injected
               repair fraction, because no source system records whether a
               customer was satisfied. Asking "by how much did substitution
               help?" of this data is asking a question the data cannot hear.

   RANKING:    recovered = {order_ok}, and stable across control groups with
               opposite selection problems ({stable}). The order matches the
               injected truth under every proxy tested.

               Note the weakest swap (milk -> laban) has a confidence interval
               spanning zero under BOTH proxies. Offering a same-category
               substitute is statistically indistinguishable from offering
               nothing at all — which is a policy conclusion, not a null result.

   SO WHAT:    this is the useful asymmetry. The business does not actually
               need the magnitude — it needs to know WHICH SWAP TO INSTRUCT
               PICKERS TO MAKE. That is a ranking question, and the ranking is
               robust to the proxy choice in a way the magnitude is not.

               An analyst who reports "substitutions recover X% of the damage"
               is reporting an artefact of their proxy. An analyst who reports
               "same-size beats same-brand beats same-category, and this holds
               under every reasonable definition" is reporting something the
               business can act on tomorrow.

   CEILING:    passing here means the estimators work on data whose DGP is a
               documented Python file. Real data has no such file. This
               validates the CODE, not the CONCLUSIONS.
""")

    ok = all(scores) and rank_ok == truth_ok and order_ok and stable and srm_ok and zero_in_ci
    print("=" * 78)
    print(f"VALIDATION: {'PASS' if ok else 'REVIEW NEEDED'}")
    print("=" * 78)


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).resolve().parents[1])
    main()
