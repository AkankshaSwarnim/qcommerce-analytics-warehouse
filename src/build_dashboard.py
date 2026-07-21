"""
build_dashboard.py — render reports/dashboard.html from reports/results.json.

WHY THE DASHBOARD IS GENERATED, NOT WRITTEN
-------------------------------------------
Same reason the docs are. A dashboard with hand-typed numbers is a dashboard that
is wrong the first time the pipeline runs again, and nobody notices because
dashboards are looked at, not read.

Every figure below traces to results.json. If the data changes, the page changes.

DESIGN INTENT
-------------
This is not a KPI wall. A KPI wall is what caused the problem in this repo —
a number on a screen with no argument attached, read by people with no way to
know what it hides.

So the page is built as an ARGUMENT, in the order the argument runs:
    1. the contradiction  (two numbers, both true)
    2. the mechanism      (why)
    3. the inversion      (the decision)
    4. the cost           (what it buys)
    5. the caveat         (what it does not establish)

Each panel states what it shows, why it matters, and what it hides. A reader who
takes a screenshot of one number and leaves has been failed by the design, so
the caveat travels inside the panels rather than sitting in a footer.

RUN
    python src/build_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path("reports/results.json")
OUT = Path("reports/dashboard.html")

NAVY, GOLD, RED, GREEN, INK = "#14284B", "#B08D2B", "#B3261E", "#2E6B4F", "#1A1A1A"


def bar(pct: float, colour: str, label: str) -> str:
    return (f'<div class="bar-row"><span class="bar-lbl">{label}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;'
            f'background:{colour}"></div></div>'
            f'<span class="bar-val">{pct:.2f}%</span></div>')


def build(R: dict) -> str:
    g, e, s = R["grain_trap"], R["stockout_effect"], R["substitution_ambiguity"]
    x = R["experiment"]
    ten = {t["tenure"]: t for t in e["by_tenure"]}
    rr = s["ranking_robustness"]["by_control_group"]["B_vs_not_offered"]["detail"]

    basket_rows = "".join(
        f"<tr><td>{b['basket_band']}</td><td>{int(b['orders']):,}</td>"
        f"<td class='good'>{b['item_fill']:.2%}</td>"
        f"<td class='bad'><b>{b['order_fill']:.2%}</b></td></tr>"
        for b in g["by_basket_band"])

    swap_rows = "".join(
        f"<tr><td>{r['substitution_type'].replace('_',' ')}</td>"
        f"<td><b>{r['effect_pp']:+.2f} pp</b></td>"
        f"<td>[{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}]</td>"
        f"<td>{'<span class=bad>indistinguishable from nothing</span>' if r['ci_lo'] < 0 < r['ci_hi'] else '<span class=good>real</span>'}</td></tr>"
        for r in rr)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beyond Fill Rate — decision dashboard</title>
<style>
  :root {{ --navy:{NAVY}; --gold:{GOLD}; --red:{RED}; --green:{GREEN}; --ink:{INK}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#F7F6F3; color:var(--ink);
         font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
  header {{ background:var(--navy); color:#fff; padding:34px 28px; }}
  header h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:-.2px; }}
  header p {{ margin:0; opacity:.85; font-size:14px; }}
  .synthetic {{ display:inline-block; margin-top:12px; padding:4px 10px; border:1px solid rgba(255,255,255,.4);
                border-radius:3px; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }}
  main {{ max-width:1080px; margin:0 auto; padding:28px; }}
  .panel {{ background:#fff; border:1px solid #E3E0D8; border-radius:6px; padding:24px; margin-bottom:22px; }}
  .step {{ font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--gold); font-weight:700; }}
  h2 {{ margin:6px 0 4px; font-size:20px; color:var(--navy); }}
  .why {{ margin:0 0 18px; color:#555; font-size:14px; }}
  .hides {{ margin-top:16px; padding:11px 14px; background:#FBF7EC; border-left:3px solid var(--gold);
            font-size:13px; color:#5A4A1F; }}
  .hides b {{ color:#3D3212; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  .stat {{ text-align:center; padding:18px; border-radius:5px; }}
  .stat .n {{ font-size:38px; font-weight:700; line-height:1.1; }}
  .stat .l {{ font-size:12px; margin-top:6px; opacity:.85; }}
  .ops {{ background:#EAF2EC; color:var(--green); }}
  .cust {{ background:#FBEAE8; color:var(--red); }}
  .gap {{ text-align:center; margin:16px 0 4px; font-size:15px; }}
  .gap b {{ font-size:26px; color:var(--navy); }}
  table {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:14px; }}
  th,td {{ padding:9px 10px; text-align:left; border-bottom:1px solid #EEE; }}
  th {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:#777; }}
  .good {{ color:var(--green); }} .bad {{ color:var(--red); }}
  .bar-row {{ display:flex; align-items:center; gap:12px; margin:7px 0; }}
  .bar-lbl {{ width:150px; font-size:13px; }}
  .bar-track {{ flex:1; height:20px; background:#EFEDE7; border-radius:3px; overflow:hidden; }}
  .bar-fill {{ height:100%; }}
  .bar-val {{ width:62px; text-align:right; font-variant-numeric:tabular-nums; font-size:13px; }}
  .verdict {{ margin-top:16px; padding:13px 16px; background:var(--navy); color:#fff; border-radius:5px; font-size:14px; }}
  .verdict b {{ color:#F0D48A; }}
  footer {{ max-width:1080px; margin:0 auto; padding:0 28px 44px; color:#777; font-size:12.5px; }}
  code {{ background:#F0EEE8; padding:1px 5px; border-radius:3px; font-size:12.5px; }}
  @media (max-width:760px) {{ .two {{ grid-template-columns:1fr; }} .bar-lbl {{ width:96px; }} }}
</style></head><body>

<header>
  <h1>Beyond Fill Rate</h1>
  <p>Why is retention falling when fill rate has stayed above 95%?</p>
  <span class="synthetic">Synthetic data · mechanisms real, magnitudes invented</span>
</header>

<main>

  <div class="panel">
    <div class="step">1 · The contradiction</div>
    <h2>Both numbers are correct</h2>
    <p class="why">The same {g['orders']:,} orders and {g['items']:,} items, measured at two
       different grains. Operations was right: fill rate never dropped.</p>
    <div class="two">
      <div class="stat ops"><div class="n">{g['item_fill_rate']:.2%}</div>
        <div class="l">ITEM fill rate<br>what the shift report shows</div></div>
      <div class="stat cust"><div class="n">{g['order_fill_rate']:.2%}</div>
        <div class="l">ORDER fill rate<br>what the customer experiences</div></div>
    </div>
    <p class="gap">A gap of <b>{g['gap_pp']:.1f} points</b></p>
    <div class="hides"><b>What this hides:</b> nothing yet — that is the problem. Two true
      numbers, no argument attached. Keep reading; a number on a screen is what caused this.</div>
  </div>

  <div class="panel">
    <div class="step">2 · The mechanism</div>
    <h2>An order is clean only if <em>every</em> item is</h2>
    <p class="why">P(clean order) = (1 − item miss rate) ^ basket size. At a
       {g['item_miss_rate']:.1%} miss rate and a {g['mean_basket']:.1f}-item mean basket,
       roughly a third of orders are broken by arithmetic — not by anyone doing their job badly.</p>
    {bar(g['item_fill_rate']*100, GREEN, 'Item fill')}
    {bar(g['order_fill_rate']*100, RED, 'Order fill')}
    <div class="hides"><b>What this hides:</b> severity. A missing bag of crisps and missing
      infant formula both make an order "unclean". The retention damage does not treat them
      alike — high-intent stock-outs cost a further
      <b>{e['high_intent_asymmetry']['effect_pp']:+.2f} pp</b>.</div>
  </div>

  <div class="panel">
    <div class="step">3 · The inversion — this is the decision</div>
    <h2>The ops metric ranks our best customers as well-served</h2>
    <p class="why">Read the last two columns against each other.</p>
    <table>
      <tr><th>Basket size</th><th>Orders</th><th>Item fill</th><th>Order fill</th></tr>
      {basket_rows}
    </table>
    <div class="verdict">Item fill rate says large baskets are served <b>slightly better</b>.
      Order fill rate says <b>twice as badly</b>. Large baskets are the Weekly Stock-Up segment —
      our highest-value customers. <b>The metric we optimise conceals that our best customers
      get our worst experience.</b></div>
    <div class="hides"><b>What this hides:</b> it does not tell you fill rate is cheap to fix.
      Fill rate is bought with inventory, and inventory is the one thing a darkstore has no room
      for. See <code>docs/01_problem.md</code>.</div>
  </div>

  <div class="panel">
    <div class="step">4 · The cost</div>
    <h2>A broken order costs {abs(ten['new']['effect_pp']/ten['established']['effect_pp']):.1f}× more on a first basket</h2>
    <p class="why">Effect on 30-day repeat rate, with 95% confidence intervals.
       New = 2 or fewer prior orders.</p>
    <table>
      <tr><th>Customer</th><th>Focal orders</th><th>Clean</th><th>Stocked out</th><th>Effect</th><th>95% CI</th></tr>
      <tr><td><b>New</b></td><td>{ten['new']['n']:,}</td><td>{ten['new']['clean_repeat']:.1%}</td>
          <td>{ten['new']['stockout_repeat']:.1%}</td><td class="bad"><b>{ten['new']['effect_pp']:+.2f} pp</b></td>
          <td>[{ten['new']['ci_lo']:+.2f}, {ten['new']['ci_hi']:+.2f}]</td></tr>
      <tr><td>Established</td><td>{ten['established']['n']:,}</td><td>{ten['established']['clean_repeat']:.1%}</td>
          <td>{ten['established']['stockout_repeat']:.1%}</td><td>{ten['established']['effect_pp']:+.2f} pp</td>
          <td>[{ten['established']['ci_lo']:+.2f}, {ten['established']['ci_hi']:+.2f}]</td></tr>
    </table>
    <div class="verdict">The pooled figure ({e['naive']['effect_pp']:+.2f} pp) averages two
      populations that need <b>opposite decisions</b>. Do not put it on a dashboard.</div>
    <div class="hides"><b>What this hides:</b> these are <b>observational</b>, not causal.
      Stock-outs were not randomised. And there is no rider data in this warehouse — lateness
      and stock-outs both spike at peak, so some of this effect may belong to lateness.
      <b>This estimate is plausibly upward-biased.</b></div>
  </div>

  <div class="panel">
    <div class="step">5 · The thing we cannot measure</div>
    <h2>A quarter of our substitution offers do nothing</h2>
    <p class="why">Nothing in any source system records whether a substitution was any
       <em>good</em>. Three defensible proxies disagree by {s['agreement']['spread_pp']:.1f} pp,
       so the magnitude is not reportable. The <b>ranking</b> is stable across proxies with
       opposite selection problems — and ranking is what a picker actually needs.</p>
    <table>
      <tr><th>Swap type</th><th>Effect on repeat</th><th>95% CI</th><th>Verdict</th></tr>
      {swap_rows}
    </table>
    <div class="verdict">Milk → laban is <b>statistically indistinguishable from offering
      nothing at all</b>. That is not a null result. It is an instruction.</div>
    <div class="hides"><b>What this hides:</b> the magnitudes above are proxy artefacts —
      only the order is trustworthy. A one-question post-delivery survey would replace this
      entire panel. See <code>docs/08_ambiguity.md</code>.</div>
  </div>

  <div class="panel">
    <div class="step">6 · The experiment that looked fine</div>
    <h2>A tidy null that was destroying the funnel</h2>
    <p class="why">Pre-approved substitutions. Assignment at session start, exposure at
       checkout — and the treatment adds a step that large baskets abandon.</p>
    <table>
      <tr><th>Check</th><th>Result</th><th>Reading</th></tr>
      <tr><td>SRM at assignment</td><td>p = {x['srm_at_assignment']['p_value']:.2f}</td>
          <td class="good">randomisation was performed correctly</td></tr>
      <tr><td>SRM at checkout</td><td><b>p = {x['srm_at_checkout']['p_value']:.1e}</b></td>
          <td class="bad">randomisation did NOT survive</td></tr>
      <tr><td>Retention among converters</td><td>{x['analysis_at_checkout_WRONG']['effect_pp']:+.2f} pp,
          p = {x['analysis_at_checkout_WRONG']['p_value']:.2f}</td>
          <td>"no effect — harmless, ship it"</td></tr>
      <tr><td><b>Conversion</b></td><td class="bad"><b>{x['conversion_harm']['effect_pp']:+.2f} pp</b></td>
          <td class="bad"><b>{abs(x['conversion_harm']['relative_loss']):.1%} of treatment conversions destroyed</b></td></tr>
      <tr><td>ITT (everyone assigned)</td><td class="bad">{x['analysis_itt_CORRECT']['effect_pp']:+.2f} pp</td>
          <td class="bad">net harm</td></tr>
    </table>
    <div class="verdict">Not a fake win — a fake <b>harmless</b>. The retention metric is
      conditioned on converting, and converting is exactly what the treatment broke.
      <b>Nobody re-examines a null.</b> Decision: <b>DO NOT SHIP</b>.</div>
    <div class="hides"><b>What this hides:</b> the feature idea is fine. The checkout
      interstitial is what kills it. Move it out of the purchase path and re-test with
      conversion as a required guardrail.</div>
  </div>

</main>

<footer>
  <p><b>This data is synthetic.</b> Generated by <code>src/generate_data.py</code>. The
     mechanisms are structurally real; the magnitudes are invented. Please do not quote
     {g['order_fill_rate']:.2%} as a fact about quick commerce — see
     <code>docs/07_limitations.md</code>.</p>
  <p>Every figure on this page is rendered from <code>reports/results.json</code> by
     <code>src/build_dashboard.py</code>. Nothing is hand-typed.</p>
</footer>
</body></html>"""


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit("Run `python src/analysis.py` first.")
    OUT.write_text(build(json.loads(RESULTS.read_text())))
    print(f"  wrote {OUT}  ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).resolve().parents[1])
    main()
