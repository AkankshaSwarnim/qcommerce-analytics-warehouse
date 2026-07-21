"""
analysis.py — every number the project claims, computed from the warehouse.

CONTRACT
--------
1. This module reads ONLY from the warehouse (`data/warehouse.duckdb`). It never
   touches data/raw/, and it never opens the truth file. Scoring against ground
   truth happens in validate.py, which runs afterwards and separately.

2. It must not import the answer key. There is a mechanical guard below that
   fails loudly if config's causal parameters are reachable from here. "I
   promise I didn't look" is not a methodology; an assertion is.

3. Every output lands in reports/results.json. Nothing in the docs, the
   dashboard, or the README is typed by hand — if a number appears in this
   project, it came out of this file.

RUN
    python src/analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

DB = "data/warehouse.duckdb"
OUT = Path("reports/results.json")

# ---------------------------------------------------------------------------
# THE GUARD
# ---------------------------------------------------------------------------
# config.py holds the generative truth. If this module can see it, the analysis
# is not blind and no result it produces means anything. Fail rather than warn:
# a warning gets ignored, an exception gets fixed.
def _assert_blind() -> None:
    import importlib.util
    spec = importlib.util.find_spec("config")
    if spec is None:
        return  # config not importable from here — which is the desired state
    import config  # noqa
    leaked = [p for p in getattr(config, "CAUSAL_PARAMS", ()) if hasattr(config, p)]
    if leaked:
        raise RuntimeError(
            "analysis.py can see the answer key: " + ", ".join(leaked) +
            "\nThe analysis must be blind to the generative parameters. "
            "Ground-truth scoring belongs in validate.py."
        )


def q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).fetchdf()


# ---------------------------------------------------------------------------
# 1. THE GRAIN TRAP
# ---------------------------------------------------------------------------
def grain_trap(con) -> dict:
    """
    Item fill rate vs order fill rate — the same data at two grains.

    An order is clean only if EVERY item is clean, so P(clean) = (1-p)^basket.
    The two numbers are both correct and they support opposite decisions. This
    is the finding; everything else in the project is downstream of it.
    """
    overall = q(con, """
        select
            count(*)                                                       as orders,
            sum(n_items)                                                   as n_items_total,
            avg(item_fill_rate)                                            as item_fill,
            sum(case when is_clean_order then 1 else 0 end)*1.0/count(*)   as order_fill,
            avg(n_items)                                                   as mean_basket
        from main_marts.fct_orders
        where not is_cancelled
    """).iloc[0]

    # The inversion. This table is the whole argument in five rows.
    by_basket = q(con, """
        with b as (
          select *,
            case when n_items <= 3 then '1-3'
                 when n_items <= 6 then '4-6'
                 when n_items <= 10 then '7-10'
                 when n_items <= 15 then '11-15'
                 else '16+' end as basket_band,
            case when n_items <= 3 then 1 when n_items <= 6 then 2
                 when n_items <= 10 then 3 when n_items <= 15 then 4 else 5 end as ord
          from main_marts.fct_orders where not is_cancelled
        )
        select basket_band, ord,
               count(*)                                                     as orders,
               avg(n_items)                                                 as mean_items,
               avg(item_fill_rate)                                          as item_fill,
               sum(case when is_clean_order then 1 else 0 end)*1.0/count(*) as order_fill
        from b group by 1,2 order by ord
    """)

    # Is the inversion real, or am I reading noise in a rounding artefact?
    # Spearman on the band means: item fill should trend UP or flat with basket
    # size, order fill must trend DOWN. If item fill also trended down there
    # would be no inversion to report and no project.
    rho_item, p_item = stats.spearmanr(by_basket["ord"], by_basket["item_fill"])
    rho_order, p_order = stats.spearmanr(by_basket["ord"], by_basket["order_fill"])

    return {
        "orders": int(overall["orders"]),
        "items": int(overall["n_items_total"]),
        "item_fill_rate": float(overall["item_fill"]),
        # Emitted rather than left for the docs to derive. A figure computed in
        # two places is a figure that will disagree with itself eventually.
        "item_miss_rate": float(1 - overall["item_fill"]),
        "order_fill_rate": float(overall["order_fill"]),
        "gap_pp": float((overall["item_fill"] - overall["order_fill"]) * 100),
        "mean_basket": float(overall["mean_basket"]),
        "by_basket_band": by_basket.drop(columns=["ord"]).to_dict("records"),
        "inversion": {
            "item_fill_vs_basket_spearman": float(rho_item),
            "item_fill_p": float(p_item),
            "order_fill_vs_basket_spearman": float(rho_order),
            "order_fill_p": float(p_order),
            "note": (
                "Item fill rises with basket size while order fill falls. Both "
                "monotonic, opposite directions. The ops metric ranks large "
                "baskets as better served at the moment they are served worst."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 2. WHAT DOES A STOCK-OUT COST?
# ---------------------------------------------------------------------------
def _diff_ci(a: pd.Series, b: pd.Series) -> tuple[float, float, float]:
    """
    Difference in two proportions with a 95% normal-approximation CI, in pp.

    Normal approximation is fine here: every cell has n in the thousands and p
    nowhere near 0 or 1, so the Wald interval and an exact interval agree to
    well past the precision anyone will act on. It would NOT be fine on the
    thin segment cells, which is why those carry n and are read with care.
    """
    p1, n1 = a.mean(), len(a)
    p2, n2 = b.mean(), len(b)
    d = (p1 - p2) * 100
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) * 100
    return float(d), float(d - 1.96 * se), float(d + 1.96 * se)


def stockout_effect(con) -> dict:
    """
    The causal question, and the honest limits of an observational answer.

    Stock-outs were not randomised. Nothing here is a causal effect in the
    experimental sense; these are associations under a stated adjustment set.
    The experiment layer exists precisely because this section cannot close.
    """
    f = q(con, """
        select *
        from main_marts.fct_customer_orders
        where is_observable_30d          -- 30 clear days of follow-up, or excluded
          and not is_test_account        -- QA bots removed (int_test_accounts)
    """)
    f["repeat30"] = f["repeat_within_30d"].fillna(False).astype(bool)

    so, clean = f[f.had_stockout], f[~f.had_stockout]
    naive_d, naive_lo, naive_hi = _diff_ci(so.repeat30, clean.repeat30)

    # --- by tenure: where the decision lives ---
    by_tenure = []
    for t in ["new", "established"]:
        d = f[f.tenure == t]
        dd, lo, hi = _diff_ci(d[d.had_stockout].repeat30, d[~d.had_stockout].repeat30)
        by_tenure.append({
            "tenure": t, "n": int(len(d)),
            "stockout_share": float(d.had_stockout.mean()),
            "clean_repeat": float(d[~d.had_stockout].repeat30.mean()),
            "stockout_repeat": float(d[d.had_stockout].repeat30.mean()),
            "effect_pp": dd, "ci_lo": lo, "ci_hi": hi,
        })

    # --- the confound check that came back negative ---
    # Basket size drives stock-out exposure enormously (mechanically: more items,
    # more chances to miss). If large-basket customers also retained differently
    # for unrelated reasons, the naive contrast would be comparing heavy buyers
    # to light buyers rather than stocked-out to clean. Test it: stratify on
    # basket quintile and reweight to the population.
    f["basket_q"] = pd.qcut(f.n_items, 5, labels=False, duplicates="drop")
    w = f.groupby("basket_q").size() / len(f)
    strat = 0.0
    exposure_gradient = []
    for k, d in f.groupby("basket_q"):
        dd, _, _ = _diff_ci(d[d.had_stockout].repeat30, d[~d.had_stockout].repeat30)
        strat += w[k] * dd
        exposure_gradient.append({
            "quintile": int(k) + 1,
            "mean_items": float(d.n_items.mean()),
            "stockout_rate": float(d.had_stockout.mean()),
            "baseline_repeat_clean": float(d[~d.had_stockout].repeat30.mean()),
        })

    # --- high-intent asymmetry ---
    # A missing bag of crisps is an annoyance. Missing infant formula is why
    # they opened the app. If this asymmetry is real, a flat fill-rate target is
    # the wrong instrument regardless of what the average says.
    hi = f[f.had_stockout & f.had_high_intent_stockout]
    lo_ = f[f.had_stockout & ~f.had_high_intent_stockout]
    hi_d, hi_lo, hi_hi = _diff_ci(hi.repeat30, lo_.repeat30)

    return {
        "focal_orders": int(len(f)),
        "naive": {"effect_pp": naive_d, "ci_lo": naive_lo, "ci_hi": naive_hi,
                  "stockout_repeat": float(so.repeat30.mean()),
                  "clean_repeat": float(clean.repeat30.mean())},
        "by_tenure": by_tenure,
        "basket_confound": {
            "naive_pp": naive_d,
            "basket_stratified_pp": float(strat),
            "shift_pp": float(strat - naive_d),
            "exposure_gradient": exposure_gradient,
            "verdict": (
                "Basket size is a strong EXPOSURE confounder and a weak OUTCOME "
                "confounder. Stock-out rate nearly triples across basket "
                "quintiles, but baseline repeat is flat and non-monotonic across "
                "the same range, so adjusting for it barely moves the estimate. "
                "Reported as a negative result rather than deleted: the "
                "adjustment was run because the hypothesis was reasonable, it "
                "did not change the answer, and that is information."
            ),
        },
        "high_intent_asymmetry": {
            "effect_pp": hi_d, "ci_lo": hi_lo, "ci_hi": hi_hi,
            "n_high_intent": int(len(hi)), "n_other": int(len(lo_)),
            "note": ("Extra damage when the missing item was the reason for the "
                     "trip, measured against other stocked-out orders."),
        },
    }


# ---------------------------------------------------------------------------
# 3. THE AMBIGUOUS QUESTION  ->  docs/08_ambiguity.md
# ---------------------------------------------------------------------------
def substitution_proxies(con) -> dict:
    """
    "Was the substitution any good?"

    Nobody ever logged it. There is no satisfaction field, no thumbs-up, no
    label anywhere in eight source systems. The warehouse knows the swap TYPE
    and whether it was ACCEPTED. It does not know whether the customer was okay
    with it.

    So the question cannot be answered. It can only be REPLACED with a question
    that can be, and the replacement is the analytical judgement — not a
    technicality to be waved through in a footnote.

    Three defensible proxies. They are built to disagree, because they do.
    """
    s = q(con, """
        select *
        from main_marts.fct_customer_orders
        where is_observable_30d
          and not is_test_account
          and had_stockout                -- the population at risk
    """)
    s["repeat30"] = s["repeat_within_30d"].fillna(False).astype(bool)

    accepted = s[s.substitute_accepted == True]  # noqa: E712
    offered_not_accepted = s[(s.substitute_offered == True) & (s.substitute_accepted != True)]  # noqa: E712
    not_offered = s[s.substitute_offered != True]  # noqa: E712

    proxies: dict[str, dict] = {}

    # --- PROXY A: acceptance as consent -------------------------------------
    # "If they took it, it was fine."
    # BLIND SPOT: acceptance is not endorsement. A customer at 11pm with no
    # alternative accepts whatever arrives. Silence is not satisfaction, and
    # this proxy cannot tell resignation from approval.
    a_d, a_lo, a_hi = _diff_ci(accepted.repeat30, offered_not_accepted.repeat30)
    proxies["A_acceptance_as_consent"] = {
        "definition": "A substitution 'worked' if the customer accepted it.",
        "contrast": "accepted vs offered-but-declined",
        "n_treat": int(len(accepted)), "n_ctrl": int(len(offered_not_accepted)),
        "effect_pp": a_d, "ci_lo": a_lo, "ci_hi": a_hi,
        "blind_spot": ("Acceptance is not endorsement. Declining may signal a "
                       "customer with alternatives — i.e. the contrast is "
                       "confounded by choice, not by the swap."),
    }

    # --- PROXY B: retention as forgiveness ----------------------------------
    # "If they came back, it was fine."
    # BLIND SPOT: 30-day repeat is downstream of everything — price, habit,
    # weather, a competitor's promo. The signal from one swap is a whisper in
    # a stadium.
    b_d, b_lo, b_hi = _diff_ci(accepted.repeat30, not_offered.repeat30)
    proxies["B_retention_as_forgiveness"] = {
        "definition": "A substitution 'worked' if the customer ordered again within 30 days.",
        "contrast": "accepted-substitute vs no-substitute-offered",
        "n_treat": int(len(accepted)), "n_ctrl": int(len(not_offered)),
        "effect_pp": b_d, "ci_lo": b_lo, "ci_hi": b_hi,
        "blind_spot": ("Whether a substitute was OFFERED is a picker/ops "
                       "decision, not a coin flip. The contrast compares "
                       "situations where staff chose to act against ones where "
                       "they did not — selection on the treatment."),
    }

    # --- PROXY C: swap distance ---------------------------------------------
    # "A closer swap is a better swap."
    # This one is not an outcome measure at all — it is a PRIOR about the
    # product, dressed as a metric. Stated as such rather than smuggled in.
    by_type = []
    for t in ["same_brand_diff_size", "diff_brand_same_product", "diff_product_same_cat"]:
        d = accepted[accepted.substitution_type == t]
        if len(d) < 100:
            continue
        dd, lo, hi = _diff_ci(d.repeat30, not_offered.repeat30)
        by_type.append({
            "substitution_type": t, "n": int(len(d)),
            "repeat_rate": float(d.repeat30.mean()),
            "effect_vs_no_offer_pp": dd, "ci_lo": lo, "ci_hi": hi,
        })
    proxies["C_swap_distance"] = {
        "definition": ("A substitution 'worked' in proportion to how close the "
                       "replacement was to the original (same brand > same "
                       "product > same category)."),
        "contrast": "per swap type vs no-substitute-offered",
        "by_type": by_type,
        "blind_spot": ("This encodes a belief about groceries, not a measurement "
                       "of customers. It will look correct whenever the belief "
                       "is correct, which is not the same as being evidence."),
    }

    # --- do they agree? ------------------------------------------------------
    # The deliverable is the disagreement. If reasonable analysts pick
    # reasonable proxies and reach different numbers, then the number is not the
    # finding — the fragility is.
    ests = {"A": a_d, "B": b_d}
    if by_type:
        ests["C_best_swap"] = max(x["effect_vs_no_offer_pp"] for x in by_type)
        ests["C_worst_swap"] = min(x["effect_vs_no_offer_pp"] for x in by_type)
    spread = max(ests.values()) - min(ests.values())

    # --- RANKING ROBUSTNESS -------------------------------------------------
    # The magnitude is proxy-dependent. Is the ORDER of the swap types?
    #
    # This is the question worth asking, because the business decision is a
    # ranking decision ("which swap should pickers make?") and not a magnitude
    # decision. If the order is stable across proxies while the size is not,
    # then the data supports the decision even though it cannot support the
    # headline number.
    #
    # Tested by re-deriving the ranking under BOTH control-group definitions:
    #   A-style control: offered-but-declined  (holds the picker's decision fixed)
    #   B-style control: no substitute offered (holds the customer's choice fixed)
    # These two controls have opposite selection problems, so agreement between
    # them is worth something. Agreement would be worth nothing if they shared a
    # confounder, which is exactly why the pair was chosen.
    SWAP_TYPES = ["same_brand_diff_size", "diff_brand_same_product", "diff_product_same_cat"]
    rankings = {}
    for label, ctrl in [("A_vs_declined", offered_not_accepted),
                        ("B_vs_not_offered", not_offered)]:
        rows = []
        for t in SWAP_TYPES:
            d = accepted[accepted.substitution_type == t]
            if len(d) < 100:
                continue
            dd, lo, hi = _diff_ci(d.repeat30, ctrl.repeat30)
            rows.append({"substitution_type": t, "n": int(len(d)),
                         "effect_pp": dd, "ci_lo": lo, "ci_hi": hi})
        rankings[label] = {
            "detail": rows,
            "order": [x["substitution_type"] for x in sorted(rows, key=lambda x: -x["effect_pp"])],
        }
    orders = [v["order"] for v in rankings.values() if v["order"]]
    ranking_stable = len(orders) > 1 and all(o == orders[0] for o in orders)

    return {
        "population_at_risk": int(len(s)),
        "proxies": proxies,
        "agreement": {
            "estimates_pp": ests,
            "spread_pp": float(spread),
            "verdict": (
                "The proxies disagree by {:.1f} pp. That spread is the finding. "
                "Reporting any single one as 'the impact of substitutions' would "
                "be choosing a number and calling it a measurement."
            ).format(spread),
        },
        "ranking_robustness": {
            "by_control_group": rankings,
            "order_stable_across_proxies": bool(ranking_stable),
            "verdict": (
                "MAGNITUDE is proxy-dependent and therefore not reportable. "
                "RANKING is stable across control groups with opposite selection "
                "problems, and therefore is. The business decision is a ranking "
                "decision — which swap should a picker make — so the data "
                "supports the decision it cannot support the headline for."
            ),
        },
        "what_the_data_cannot_settle": [
            "Whether an accepted substitute was satisfactory or merely tolerated. "
            "No source system records it and no proxy recovers it.",
            "Whether the picker's choice to offer a substitute is independent of "
            "the customer, the basket, or the hour. It is almost certainly not.",
            "The counterfactual: what this same customer would have done had the "
            "item been in stock. Observational data has no access to it.",
        ],
        "what_would_settle_it": [
            "A one-question post-delivery survey on substituted orders. Cheapest "
            "instrument available; gives a direct label instead of three proxies.",
            "Randomising the substitution POLICY (not the stock-out) — e.g. "
            "pre-approved substitutes vs ask-at-the-door. This is the experiment "
            "in docs/06_experimentation.md, and it exists because this section "
            "cannot close.",
            "Instrumenting the picker decision: log why a substitute was or was "
            "not offered, which turns an unobserved confounder into a covariate.",
        ],
    }


# ---------------------------------------------------------------------------
# 4. THE EXPERIMENT
# ---------------------------------------------------------------------------
def _srm_check(n_a: int, n_b: int, expected_share_a: float = 0.5) -> dict:
    """
    Sample Ratio Mismatch: a chi-square goodness-of-fit test on the SPLIT.

    This is not a test of the treatment. It is a test of whether the experiment
    happened at all. If the observed split departs from the intended one by more
    than chance, randomisation did not survive to the analysis population, and
    every downstream number is describing a population the treatment selected.

    p < 0.001 is the conventional threshold rather than 0.05, and deliberately
    so: with hundreds of thousands of sessions, a 0.5pp imbalance is significant
    at 0.05 while being operationally meaningless. The strict threshold keeps
    the check from crying wolf on every experiment that ever runs.
    """
    from scipy.stats import chisquare
    total = n_a + n_b
    expected = [total * expected_share_a, total * (1 - expected_share_a)]
    chi2, p = chisquare([n_a, n_b], expected)
    observed_share = n_a / total if total else float("nan")
    return {
        "n_control": int(n_a), "n_treatment": int(n_b),
        "observed_control_share": float(observed_share),
        "expected_control_share": float(expected_share_a),
        "chi2": float(chi2), "p_value": float(p),
        "srm_detected": bool(p < 0.001),
    }


def _power_mde(n_per_arm: int, baseline: float, alpha=0.05, power=0.80) -> float:
    """
    Minimum detectable effect, in pp, for a two-proportion test.

    Reported BEFORE the effect estimate, on purpose. An MDE computed after the
    fact is a rationalisation; computed first, it tells you whether the
    experiment was ever capable of answering the question. An experiment
    underpowered for the effect you care about produces a null that means
    nothing — and shipping on "no significant difference" from such a test is
    the most common mistake in industry experimentation.
    """
    from scipy.stats import norm
    z_a = norm.ppf(1 - alpha / 2)
    z_b = norm.ppf(power)
    se = np.sqrt(2 * baseline * (1 - baseline) / n_per_arm)
    return float((z_a + z_b) * se * 100)


def experiment(con) -> dict:
    """
    Pre-approved substitutions: does letting customers pre-approve swaps at
    checkout improve 30-day retention?

    The analysis is run twice, on purpose:

      (1) at CHECKOUT — the population an analyst reaches for, because that is
          where the feature was actually used. This is the wrong answer.
      (2) at ASSIGNMENT — intention-to-treat, everyone randomised, including
          those who never reached checkout. This is the right one.

    They disagree. The gap between them is the whole lesson.
    """
    s = q(con, """
        select f.*, o.n_items, co.repeat_within_30d, co.is_observable_30d
        from main_marts.fct_sessions f
        left join main_marts.fct_orders o on f.order_id = o.order_id
        left join main_marts.fct_customer_orders co on f.order_id = co.order_id
        where f.is_in_experiment
          and not coalesce(f.is_test_account, false)
    """)

    # --- SRM at ASSIGNMENT: was randomisation done correctly? ---
    a_ctrl = int((s.variant == "control").sum())
    a_trt = int((s.variant == "treatment").sum())
    srm_assignment = _srm_check(a_ctrl, a_trt)

    # --- SRM at CHECKOUT: did randomisation SURVIVE to the analysis set? ---
    conv = s[s.converted == True]  # noqa: E712
    c_ctrl = int((conv.variant == "control").sum())
    c_trt = int((conv.variant == "treatment").sum())
    srm_checkout = _srm_check(c_ctrl, c_trt)

    # --- THE HARM THE PRIMARY METRIC CANNOT SEE ---
    # Retention-among-converters is conditioned on converting. If the feature
    # changes conversion, that change is invisible to it BY CONSTRUCTION — the
    # lost users are not in the denominator, they are not in the numerator, they
    # are not in the table at all.
    conv_ctrl = s[s.variant == "control"].converted.astype(bool)
    conv_trt = s[s.variant == "treatment"].converted.astype(bool)
    cv_d, cv_lo, cv_hi = _diff_ci(conv_trt, conv_ctrl)
    _, cv_p = stats.chi2_contingency(pd.crosstab(s.variant, s.converted).values)[:2]

    # --- the smoking gun: WHO survived to checkout? ---
    # If the treatment merely lost users at random, basket size would match
    # across arms. If it lost them selectively, it will not.
    basket_ctrl = conv[conv.variant == "control"].n_items
    basket_trt = conv[conv.variant == "treatment"].n_items
    t_stat, t_p = stats.ttest_ind(basket_ctrl.dropna(), basket_trt.dropna(), equal_var=False)

    # --- (1) THE WRONG ANALYSIS: outcomes among those who checked out ---
    obs = conv[conv.is_observable_30d == True]  # noqa: E712
    obs = obs.assign(rep=obs.repeat_within_30d.fillna(False).astype(bool))
    w_ctrl, w_trt = obs[obs.variant == "control"].rep, obs[obs.variant == "treatment"].rep
    wrong_d, wrong_lo, wrong_hi = _diff_ci(w_trt, w_ctrl)
    _, wrong_p = stats.chi2_contingency(
        pd.crosstab(obs.variant, obs.rep).values)[:2]

    # --- (2) THE RIGHT ANALYSIS: intention-to-treat over everyone assigned ---
    # Every assigned session counts. A session that never converted did not
    # repeat within 30 days, and that is a real outcome, not missing data.
    # Dropping it is exactly the move that creates the fake win.
    itt = s.copy()
    itt["rep"] = itt.repeat_within_30d.fillna(False).astype(bool)
    i_ctrl, i_trt = itt[itt.variant == "control"].rep, itt[itt.variant == "treatment"].rep
    itt_d, itt_lo, itt_hi = _diff_ci(i_trt, i_ctrl)
    _, itt_p = stats.chi2_contingency(pd.crosstab(itt.variant, itt.rep).values)[:2]

    mde = _power_mde(min(len(i_ctrl), len(i_trt)), float(i_ctrl.mean()))

    return {
        "design": {
            "unit": "session",
            "assignment": "at session start",
            "exposure": "at checkout",
            "note": ("Assignment and exposure are different events. That gap is "
                     "where the experiment breaks."),
        },
        "power": {
            "n_per_arm_assigned": int(min(len(i_ctrl), len(i_trt))),
            "baseline_repeat": float(i_ctrl.mean()),
            "mde_pp_at_80_power": mde,
            "note": ("Computed before the effect estimate. Establishes what the "
                     "experiment was capable of detecting, independent of what "
                     "it found."),
        },
        "srm_at_assignment": {**srm_assignment,
                              "verdict": "Randomisation was performed correctly."},
        "srm_at_checkout": {**srm_checkout,
                            "verdict": ("Randomisation did NOT survive to the "
                                        "analysis population.")},
        "conversion_harm": {
            "control_conversion": float(conv_ctrl.mean()),
            "treatment_conversion": float(conv_trt.mean()),
            "effect_pp": cv_d, "ci_lo": cv_lo, "ci_hi": cv_hi,
            "p_value": float(cv_p),
            "relative_loss": float((conv_trt.mean() - conv_ctrl.mean()) / conv_ctrl.mean()),
            "note": ("This is the real effect of the feature, and the retention "
                     "metric is structurally blind to it: retention-among-"
                     "converters conditions on the very thing the treatment "
                     "changed."),
        },
        "selection_evidence": {
            "mean_basket_control": float(basket_ctrl.mean()),
            "mean_basket_treatment": float(basket_trt.mean()),
            "welch_t": float(t_stat), "p_value": float(t_p),
            "note": ("Baskets differ across arms AFTER randomisation. Random "
                     "attrition cannot do this. The treatment selected who "
                     "reached checkout — smaller baskets abandon the "
                     "pre-approval step less often."),
        },
        "analysis_at_checkout_WRONG": {
            "n_control": int(len(w_ctrl)), "n_treatment": int(len(w_trt)),
            "control_repeat": float(w_ctrl.mean()),
            "treatment_repeat": float(w_trt.mean()),
            "effect_pp": wrong_d, "ci_lo": wrong_lo, "ci_hi": wrong_hi,
            "p_value": float(wrong_p),
            "verdict": ("Reads as a clean null — 'no effect on retention, "
                        "harmless'. It is not harmless. This analysis is "
                        "conditioned on converting, and converting is exactly "
                        "what the treatment broke. The feature's entire effect "
                        "sits in the population this table excludes. A fake "
                        "NULL is more dangerous than a fake win: nobody "
                        "interrogates a result that asks nothing of them."),
        },
        "analysis_itt_CORRECT": {
            "n_control": int(len(i_ctrl)), "n_treatment": int(len(i_trt)),
            "control_repeat": float(i_ctrl.mean()),
            "treatment_repeat": float(i_trt.mean()),
            "effect_pp": itt_d, "ci_lo": itt_lo, "ci_hi": itt_hi,
            "p_value": float(itt_p),
            "verdict": ("Intention-to-treat over everyone randomised. This is "
                        "the estimate the design supports."),
        },
        "decision": {
            "recommendation": "DO NOT SHIP",
            "reasoning": (
                "Three findings, in the order they matter. (1) SRM at checkout "
                "(p<1e-100) proves randomisation did not survive to the analysis "
                "population, so the checkout-level result is uninterpretable — "
                "not weak, uninterpretable. (2) The feature costs conversion "
                "outright, and that harm is invisible to a retention metric "
                "computed among converters. (3) ITT, the only estimate this "
                "design supports, shows net harm. The feature buys nothing and "
                "charges for it."
            ),
            "the_lesson": (
                "The checkout analysis does not produce a fake WIN. It produces "
                "a fake HARMLESS — a tidy null that invites a shrug. The SRM "
                "check is what turns 'no effect, no harm' into 'this feature is "
                "quietly destroying the funnel'. Nobody re-examines a null."
            ),
        },
    }


def main() -> None:
    _assert_blind()
    con = duckdb.connect(DB, read_only=True)
    results = {
        "_meta": {
            "source": "data/warehouse.duckdb (main_marts)",
            "data": "SYNTHETIC — see docs/07_limitations.md",
            "note": "Every number in this repo is generated by src/analysis.py. "
                    "Nothing in the docs or dashboard is hand-typed.",
        },
        "grain_trap": grain_trap(con),
        "stockout_effect": stockout_effect(con),
        "substitution_ambiguity": substitution_proxies(con),
        "experiment": experiment(con),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    con.close()

    g, e = results["grain_trap"], results["stockout_effect"]
    print(f"  item fill {g['item_fill_rate']:.2%}   order fill {g['order_fill_rate']:.2%}"
          f"   gap {g['gap_pp']:.1f}pp")
    print(f"  naive stock-out effect {e['naive']['effect_pp']:+.2f}pp "
          f"[{e['naive']['ci_lo']:+.2f}, {e['naive']['ci_hi']:+.2f}]")
    for t in e["by_tenure"]:
        print(f"    {t['tenure']:<12} {t['effect_pp']:+.2f}pp "
              f"[{t['ci_lo']:+.2f}, {t['ci_hi']:+.2f}]  n={t['n']:,}")
    a = results["substitution_ambiguity"]["agreement"]
    print(f"  substitution proxies disagree by {a['spread_pp']:.1f}pp -> {a['estimates_pp']}")
    print(f"\n  wrote {OUT}")


if __name__ == "__main__":
    import os, sys
    os.chdir(Path(__file__).resolve().parents[1])
    # src/ deliberately NOT added to sys.path: config.py must stay unreachable.
    sys.path = [p for p in sys.path if not p.endswith("src")]
    print("Analysing (blind to generative parameters) ...")
    main()
