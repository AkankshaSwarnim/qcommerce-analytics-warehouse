"""
render_docs.py — write the prose documents from reports/results.json.

WHY THIS REPLACED check_docs.py's ORIGINAL JOB
----------------------------------------------
The first approach was: hand-write the docs, then run a checker that greps every
"+4.01 pp" out of the prose and asserts it appears somewhere in results.json.

That checker passed on stale documents. Twice.

The reason is obvious in hindsight: results.json contains several hundred floats,
so "does this number appear ANYWHERE in the file" is a test that almost nothing
fails. It matched 94.08% against an unrelated basket-band figure and reported no
drift while the headline had moved to 94.09%. A test that cannot fail is not a
test — it is a decoration that makes you stop looking.

The structural fix is not a stricter grep. It is to stop hand-writing numbers.
Here the templates own the WORDS and this file owns the FIGURES, and the two
cannot disagree because the figures only exist in one place.

This mirrors exactly what the warehouse does with `reporting_tz`: define it once,
reference it everywhere, and the class of bug disappears rather than being
policed.

RUN
    python src/render_docs.py
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path("reports/results.json")
TEMPLATES = Path("docs/_templates")


def fields(R: dict) -> dict:
    """Every figure the templates may reference, pre-formatted."""
    g, e, s = R["grain_trap"], R["stockout_effect"], R["substitution_ambiguity"]
    x = R["experiment"]
    ten = {t["tenure"]: t for t in e["by_tenure"]}
    bc, hi = e["basket_confound"], e["high_intent_asymmetry"]
    p, rr = s["proxies"], s["ranking_robustness"]["by_control_group"]
    a = {t["substitution_type"]: t for t in rr["A_vs_declined"]["detail"]}
    b = {t["substitution_type"]: t for t in rr["B_vs_not_offered"]["detail"]}
    byt = p["C_swap_distance"]["by_type"]

    f = {
        # --- grain trap ---
        "orders": f"{g['orders']:,}",
        "items": f"{g['items']:,}",
        "item_fill": f"{g['item_fill_rate']:.2%}",
        "order_fill": f"{g['order_fill_rate']:.2%}",
        "gap_pp": f"{g['gap_pp']:.1f}",
        "item_miss": f"{g['item_miss_rate']:.1%}",
        "mean_basket": f"{g['mean_basket']:.1f}",
        "rho_item": f"{g['inversion']['item_fill_vs_basket_spearman']:+.2f}",
        "rho_order": f"{g['inversion']['order_fill_vs_basket_spearman']:+.2f}",
        "readme_basket_table": "\n".join(
            f"| {r['basket_band']} | {r['item_fill']:.2%} | **{r['order_fill']:.2%}** |"
            for r in g["by_basket_band"]),
        "basket_table": "\n".join(
            f"| {r['basket_band']} | {int(r['orders']):,} | {r['item_fill']:.2%} | {r['order_fill']:.2%} |"
            for r in g["by_basket_band"]),
        # --- stock-out ---
        "naive_pp": f"{e['naive']['effect_pp']:+.2f}",
        "strat_pp": f"{bc['basket_stratified_pp']:+.2f}",
        "shift_pp": f"{bc['shift_pp']:+.2f}",
        "gradient_table": "\n".join(
            f"| Q{r['quintile']} | {r['mean_items']:.1f} | {r['stockout_rate']:.1%} | {r['baseline_repeat_clean']:.1%} |"
            for r in bc["exposure_gradient"]),
        "hi_pp": f"{hi['effect_pp']:+.2f}",
        "hi_lo": f"{hi['ci_lo']:+.2f}", "hi_hi": f"{hi['ci_hi']:+.2f}",
        "ratio": f"{abs(ten['new']['effect_pp'] / ten['established']['effect_pp']):.1f}",
        "new_pp": f"{ten['new']['effect_pp']:+.2f}",
        "new_pp_abs": f"{abs(ten['new']['effect_pp']):.1f}",
        "new_stockout_share": f"{ten['new']['stockout_share']:.1%}",
        "est_pp": f"{ten['established']['effect_pp']:+.2f}",
        "new_share": f"{ten['new']['n'] / (ten['new']['n'] + ten['established']['n']):.0%}",
        "tenure_table": "\n".join(
            f"| {'New (≤2 prior orders)' if t['tenure']=='new' else 'Established (>2)'} "
            f"| {t['n']:,} | {t['clean_repeat']:.1%} | {t['stockout_repeat']:.1%} "
            f"| **{t['effect_pp']:+.2f} pp** | [{t['ci_lo']:+.2f}, {t['ci_hi']:+.2f}] |"
            for t in e["by_tenure"]),
        # --- ambiguity ---
        "proxy_a": f"{p['A_acceptance_as_consent']['effect_pp']:+.2f}",
        "proxy_b": f"{p['B_retention_as_forgiveness']['effect_pp']:+.2f}",
        "c_best": f"{max(t['effect_vs_no_offer_pp'] for t in byt):+.2f}",
        "c_worst": f"{min(t['effect_vs_no_offer_pp'] for t in byt):+.2f}",
        "spread": f"{s['agreement']['spread_pp']:.1f}",
        "pop_at_risk": f"{s['population_at_risk']:,}",
        "rank_table": "\n".join(
            f"| {t} | **{a[t]['effect_pp']:+.2f}** | **{b[t]['effect_pp']:+.2f}** | {a[t]['n']:,} |"
            for t in ["same_brand_diff_size", "diff_brand_same_product", "diff_product_same_cat"]),
        "worst_a_lo": f"{a['diff_product_same_cat']['ci_lo']:+.2f}",
        "worst_a_hi": f"{a['diff_product_same_cat']['ci_hi']:+.2f}",
        "worst_b_lo": f"{b['diff_product_same_cat']['ci_lo']:+.2f}",
        "worst_b_hi": f"{b['diff_product_same_cat']['ci_hi']:+.2f}",
        "rank_stable": "yes" if s["ranking_robustness"]["order_stable_across_proxies"] else "NO",
        # --- experiment ---
        "srm_p": f"{x['srm_at_checkout']['p_value']:.2g}",
        "srm_split": f"{x['srm_at_checkout']['observed_control_share']:.4f}",
        "conv_ctrl": f"{x['conversion_harm']['control_conversion']:.2%}",
        "conv_trt": f"{x['conversion_harm']['treatment_conversion']:.2%}",
        "conv_pp": f"{x['conversion_harm']['effect_pp']:+.2f}",
        "conv_rel": f"{abs(x['conversion_harm']['relative_loss']):.1%}",
        "checkout_pp": f"{x['analysis_at_checkout_WRONG']['effect_pp']:+.2f}",
        "checkout_p": f"{x['analysis_at_checkout_WRONG']['p_value']:.3g}",
        "itt_pp": f"{x['analysis_itt_CORRECT']['effect_pp']:+.2f}",
        "itt_p": f"{x['analysis_itt_CORRECT']['p_value']:.2g}",
        "mde": f"{x['power']['mde_pp_at_80_power']:.2f}",
        "n_per_arm": f"{x['power']['n_per_arm_assigned']:,}",
        "baseline_repeat": f"{x['power']['baseline_repeat']:.1%}",
        "srm_assign_split": f"{x['srm_at_assignment']['observed_control_share']:.4f}",
        "srm_assign_p": f"{x['srm_at_assignment']['p_value']:.2f}",
        "basket_ctrl": f"{x['selection_evidence']['mean_basket_control']:.2f}",
        "basket_trt": f"{x['selection_evidence']['mean_basket_treatment']:.2f}",
        "welch_t": f"{x['selection_evidence']['welch_t']:.1f}",
        "welch_p": f"{x['selection_evidence']['p_value']:.0e}",
    }
    # --- the memo's break-even, computed rather than typed -------------------
    # These are ARITHMETIC over stated assumptions, not findings. The
    # assumptions live here, beside the numbers they produce, so a reader can
    # change one and see the whole memo move. A hand-typed break-even is a
    # number that drifts from its own premises the first time the data changes —
    # which it did: an earlier draft said 138/month against a true 141.
    ASSUMED_NEW_CUSTOMER_LTV_AED = 400      # arguable; sensitivity in the memo
    ASSUMED_NEW_CUSTOMERS_PER_MONTH = 5_000  # arguable
    ASSUMED_EFFECTIVENESS = 0.50             # a fix never works perfectly

    def round_sig(x: float, sig: int = 2) -> str:
        """
        Round to significant figures for prose.

        An estimate built on invented assumptions must not be quoted to the
        dirham. "AED 675,704/year" implies a precision the inputs cannot carry
        and quietly contradicts the memo's own argument about honest numbers.
        "~AED 680k" says the same thing without the false confidence.
        """
        import math
        if x == 0:
            return "0"
        d = math.ceil(math.log10(abs(x)))
        v = round(x, -(d - sig))
        return f"{v/1000:,.0f}k" if abs(v) >= 1000 else f"{v:,.0f}"

    new = ten["new"]
    lost_per_month = (ASSUMED_NEW_CUSTOMERS_PER_MONTH
                      * new["stockout_share"]
                      * abs(new["effect_pp"]) / 100)
    value_year = lost_per_month * ASSUMED_NEW_CUSTOMER_LTV_AED * 12

    f.update({
        "ltv": f"{ASSUMED_NEW_CUSTOMER_LTV_AED:,}",
        "ltv_half": f"{ASSUMED_NEW_CUSTOMER_LTV_AED // 2:,}",
        "acq_per_month": f"{ASSUMED_NEW_CUSTOMERS_PER_MONTH:,}",
        "lost_per_month": f"~{lost_per_month:.0f}",
        "value_month": round_sig(lost_per_month * ASSUMED_NEW_CUSTOMER_LTV_AED),
        "value_year": round_sig(value_year),
        "value_year_realistic": round_sig(value_year * ASSUMED_EFFECTIVENESS),
        "effectiveness": f"{ASSUMED_EFFECTIVENESS:.0%}",
    })
    return f


def main() -> int:
    if not RESULTS.exists():
        print("reports/results.json missing — run src/analysis.py first.")
        return 1
    R = json.loads(RESULTS.read_text())
    f = fields(R)

    rendered = 0
    for tmpl in sorted(TEMPLATES.glob("*.md.tmpl")):
        # README is the repo's front door and lives at the root; everything else
        # is a chapter and lives in docs/.
        out = (Path("README.md") if tmpl.name == "README.md.tmpl"
               else Path("docs") / tmpl.name.replace(".tmpl", ""))
        text = tmpl.read_text()
        try:
            text = text.format(**f)
        except KeyError as exc:
            print(f"{tmpl.name}: template references unknown field {exc}")
            return 1
        out.write_text(text)
        rendered += 1
        print(f"  rendered {out}")

    print(f"\n{rendered} document(s) rendered from {RESULTS}")
    return 0


if __name__ == "__main__":
    import os, sys
    os.chdir(Path(__file__).resolve().parents[1])
    sys.exit(main())
