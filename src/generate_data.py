"""
generate_data.py — build the synthetic source systems.

WHAT THIS PRODUCES
------------------
Eight raw files under `data/raw/`, deliberately shaped like SEPARATE SOURCE
SYSTEMS rather than one tidy table, because that separation is the entire
reason a warehouse is needed:

    raw_customers.csv              CRM export             one row per customer
    raw_products.csv               catalogue service      SCD2, price changes
    raw_darkstores.csv             ops master data        SCD2, catchment changes
    raw_sessions.csv               app analytics (UTC)    one row per session
    raw_order_events.csv           order service (UTC)    one row per event, DUPLICATES
    raw_order_items.csv            order service          one row per order-item
    raw_fulfilment_events.csv      warehouse ops          LATE-ARRIVING
    raw_experiment_assignments.csv experiment platform    assigned at session start

Different grains. Different systems. Different clocks. Different latencies.
That is the problem statement in file form.

HOW THE CAUSAL STRUCTURE WORKS
------------------------------
Customer order histories are simulated as a SEQUENTIAL process, not drawn
independently, because the claim under test is sequential: a stock-out on order
N changes the probability of order N+1.

    for each customer:
        t = acquisition date
        while t < end of window:
            place an order at t
            resolve stock-outs on that order   <- depends on hour, store age, category
            p_repeat = segment baseline
                       + stock-out penalty (moderated by tenure & intent)
                       + substitution repair (if offered AND accepted)
            if not repeat: customer lapses, stop
            t += gap drawn from segment order rate

The confound falls out of this structure for free, without being injected:
high-frequency segments place more orders, so they are mechanically more
exposed to stock-outs, AND they carry a higher baseline repeat probability.
Any naive "stocked-out vs not" comparison therefore mixes the treatment effect
with the segment composition. See docs/02_plan.md for why that biases the
estimate toward zero.

RUN
    python src/generate_data.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config as C

RAW = Path("data/raw")
rng = np.random.default_rng(C.SEED)

GST = timezone(timedelta(hours=4))  # Gulf Standard Time. No DST, so a fixed offset is exact.

# Fail loudly rather than renormalise silently: a quietly-rescaled answer key is
# an answer key you cannot trust.
_share_sum = sum(v["offer_share"] for v in C.SUBSTITUTION_TYPES.values())
assert abs(_share_sum - 1.0) < 1e-9, f"SUBSTITUTION_TYPES offer_share must sum to 1.0, got {_share_sum}"

SUB_TYPE_NAMES = list(C.SUBSTITUTION_TYPES)
SUB_TYPE_SHARES = [C.SUBSTITUTION_TYPES[k]["offer_share"] for k in SUB_TYPE_NAMES]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _hour_weights(segment: str) -> np.ndarray:
    """
    Order-time distribution over the 24 GST hours.

    WHY IT MATTERS: stock-out risk is a function of hour (shelves drain across
    the evening and are not restocked until morning). If order timing were
    uniform, hour would be orthogonal to everything and the peak-hour story
    would vanish. It is not uniform in reality, so it is not uniform here.
    """
    w = np.full(24, 0.6)
    w[7:10] = 1.2                      # breakfast top-up
    w[12:15] = 2.0                     # lunch
    w[19:23] = 4.2                     # dinner rush — the real peak
    w[23] = 2.5
    w[0:4] = 0.8                       # the long tail of the night
    if segment == "Late-Night Rescue":
        # This segment exists precisely because the shops are shut.
        w = np.full(24, 0.3)
        w[22:24] = 3.0
        w[0:4] = 5.0
        w[4:7] = 1.2
    elif segment == "Weekly Stock-Up":
        w[10:14] = 3.0                 # weekend-ish daytime shop
        w[19:23] = 2.0
    return w / w.sum()


def _stockout_prob(hour_gst: int, store_age_days: int) -> float:
    """
    Per-item stock-out probability.

    Modifiers are multiplicative on a base rate and are capped, because a
    probability that exceeds 1 is a bug, not a busy Tuesday.
    """
    p = C.BASE_STOCKOUT_RATE
    if 19 <= hour_gst <= 22:
        p *= C.STOCKOUT_PEAK_MULT
    elif 0 <= hour_gst <= 3:
        p *= C.STOCKOUT_LATE_NIGHT_MULT
    if store_age_days < C.STOCKOUT_NEW_STORE_DAYS:
        p *= C.STOCKOUT_NEW_STORE_MULT
    return float(min(p, 0.60))


# ---------------------------------------------------------------------------
# 1. DIMENSIONS
# ---------------------------------------------------------------------------
def gen_darkstores() -> pd.DataFrame:
    """
    Darkstore master data as SCD Type 2.

    THE REAL-WORLD ISSUE: catchment radius is not static. Ops widens or narrows
    it as rider supply changes. If you model this as a Type 1 dimension (just
    overwrite), every historical order silently inherits TODAY's catchment, and
    your delivery-time analysis restates history. That is a data model bug that
    produces confident, wrong numbers — the worst kind.
    """
    rows = []
    for sid, name, area, affluence, opened in C.DARKSTORES:
        # v1: opening catchment
        rows.append(dict(
            darkstore_id=sid, darkstore_name=name, area=area,
            affluence_index=affluence, opened_on=opened,
            catchment_radius_km=2.5, valid_from=opened, valid_to=None, is_current=True,
        ))
    df = pd.DataFrame(rows)

    # Two stores widened catchment mid-window. This is the SCD2 event.
    changes = [("DS01", C.START_DATE + timedelta(days=38), 3.4),
               ("DS04", C.START_DATE + timedelta(days=55), 3.0)]
    out = []
    for _, r in df.iterrows():
        chg = [c for c in changes if c[0] == r["darkstore_id"]]
        if not chg:
            out.append(r.to_dict())
            continue
        _, chg_date, new_radius = chg[0]
        v1 = r.to_dict()
        v1.update(valid_to=chg_date, is_current=False)
        v2 = r.to_dict()
        v2.update(catchment_radius_km=new_radius, valid_from=chg_date, valid_to=None, is_current=True)
        out += [v1, v2]
    return pd.DataFrame(out)


def gen_products() -> pd.DataFrame:
    """
    Catalogue as SCD Type 2 on price.

    THE REAL-WORLD ISSUE (two of them):
      1. Prices change. Joining an order from January to today's price restates
         January's GMV. Every finance team has been burned by this.
      2. ~3% of SKUs have a NULL category — a genuine catalogue join failure.
         The tempting fix is `WHERE category IS NOT NULL`, which silently drops
         3% of revenue from every category report. The honest fix is an
         'Unmapped' bucket that stays visible and shames someone into fixing it.
    """
    n = C.N_PRODUCTS
    pid = [f"SKU{i:05d}" for i in range(1, n + 1)]
    cat = rng.choice(C.CATEGORIES, n, p=_category_mix())
    base_price = np.round(rng.gamma(2.2, 5.5, n) + 1.5, 2)

    df = pd.DataFrame(dict(
        product_id=pid, category=cat, base_price_aed=base_price,
        valid_from=C.START_DATE, valid_to=None, is_current=True,
    ))

    # Inject the missing-category defect.
    miss = rng.random(n) < C.MISSING_CATEGORY_RATE
    df.loc[miss, "category"] = None

    # ~6% of SKUs repriced mid-window -> a second SCD2 version.
    repriced = rng.random(n) < 0.06
    v2 = df[repriced].copy()
    chg_date = C.START_DATE + timedelta(days=45)
    df.loc[repriced, "valid_to"] = chg_date
    df.loc[repriced, "is_current"] = False
    v2["base_price_aed"] = np.round(v2["base_price_aed"] * rng.uniform(1.04, 1.22, len(v2)), 2)
    v2["valid_from"] = chg_date
    return pd.concat([df, v2], ignore_index=True)


def _category_mix() -> np.ndarray:
    """Basket share by category. Fresh/dairy dominate q-commerce; pet food does not."""
    w = np.array([1.6, 1.5, 1.1, 0.9, 0.8, 1.4, 1.3, 1.0, 0.7, 0.6, 0.4, 0.3])
    return w / w.sum()


def gen_customers() -> pd.DataFrame:
    """
    CRM export.

    THE REAL-WORLD ISSUE: internal QA accounts live in the same table as real
    customers, with no flag that anyone remembers to set. They order 20x more
    than a human and convert at ~100%, so they drag every aggregate. Finding
    them is a data-profiling job, not a modelling job — you notice them because
    the tail of the order-count distribution has an impossible shape.
    """
    n = C.N_CUSTOMERS
    segs = list(C.SEGMENTS.keys())
    shares = [C.SEGMENTS[s]["share"] for s in segs]
    seg = rng.choice(segs, n, p=shares)

    # Acquisition is spread across the window, weighted early so most customers
    # have room to show a 30-day outcome.
    span = (C.END_DATE - C.START_DATE).days
    acq_offset = np.floor(rng.beta(1.4, 2.6, n) * span).astype(int)
    acq = [C.START_DATE + timedelta(days=int(d)) for d in acq_offset]

    df = pd.DataFrame(dict(
        customer_id=[f"C{i:06d}" for i in range(1, n + 1)],
        segment=seg,
        acquired_on=acq,
        home_darkstore_id=rng.choice([d[0] for d in C.DARKSTORES], n),
        is_test_account=False,
    ))

    # Plant the QA accounts. Note: they are NOT flagged in the source. The flag
    # column exists and is False for everyone — that is exactly the trap. The
    # warehouse has to detect them behaviourally.
    test_idx = rng.choice(n, C.TEST_ACCOUNT_COUNT, replace=False)
    df.loc[test_idx, "segment"] = "Top-Up Regular"
    df["gen_test_truth"] = False
    df.loc[test_idx, "gen_test_truth"] = True   # generator-only ground truth; dropped before write
    return df


# ---------------------------------------------------------------------------
# 2. THE SEQUENTIAL CUSTOMER SIMULATION  (where the causal structure lives)
# ---------------------------------------------------------------------------
def simulate_orders(customers: pd.DataFrame, stores: pd.DataFrame, products: pd.DataFrame):
    """
    Walk each customer forward in time, order by order.

    Returns (orders, items) as lists of dicts.

    This is the heart of the project. Read the loop, not the summary stats.
    """
    prod_cur = products[products.is_current | products.valid_to.notna()].copy()
    # For item sampling we only need the SKU list and its category.
    sku_pool = products.drop_duplicates("product_id")[["product_id", "category"]].reset_index(drop=True)
    sku_ids = sku_pool.product_id.to_numpy()
    sku_cats = sku_pool.category.to_numpy()
    high_intent_mask = np.isin(sku_cats, list(C.HIGH_INTENT_CATEGORIES))

    store_open = {s[0]: s[4] for s in C.DARKSTORES}

    orders, items = [], []
    order_seq = 0

    for row in customers.itertuples(index=False):
        seg_cfg = C.SEGMENTS[row.segment]
        is_test = row.gen_test_truth

        # Test accounts hammer the system: far higher rate, no lapsing.
        weekly_rate = seg_cfg["weekly_rate"] * (C.TEST_ACCOUNT_ORDER_MULT if is_test else 1.0)
        hour_w = _hour_weights(row.segment)

        t = datetime.combine(row.acquired_on, datetime.min.time(), tzinfo=GST)
        end_dt = datetime.combine(C.END_DATE, datetime.max.time(), tzinfo=GST)
        prior_orders = 0

        while t <= end_dt:
            hour = int(rng.choice(24, p=hour_w))
            ts_gst = t.replace(hour=hour, minute=int(rng.integers(0, 60)),
                               second=int(rng.integers(0, 60)), microsecond=0)
            if ts_gst > end_dt:
                break

            store = row.home_darkstore_id
            if ts_gst.date() < store_open[store]:
                # Store not open yet -> fall back to the busiest mature store.
                store = "DS02"
            store_age = (ts_gst.date() - store_open[store]).days

            # ---- basket ----
            n_items = max(1, int(rng.poisson(8 * seg_cfg["basket_mult"])))
            idx = rng.choice(len(sku_ids), n_items, replace=False)
            p_so = _stockout_prob(hour, store_age)
            so = rng.random(n_items) < p_so

            order_seq += 1
            oid = f"O{order_seq:08d}"

            any_so = bool(so.any())
            hi_so = bool((so & high_intent_mask[idx]).any())

            # ---- substitution ----
            # A substitute is offered on SOME stock-outs. Its TYPE is drawn from
            # the picker's realistic mix, and acceptance depends on the type:
            # customers happily take a bigger bottle of the same milk, and
            # mostly refuse laban-instead-of-milk.
            sub_offered = any_so and (rng.random() < C.SUBSTITUTION_OFFER_RATE)
            sub_type, sub_accepted = None, False
            if sub_offered:
                sub_type = SUB_TYPE_NAMES[int(rng.choice(len(SUB_TYPE_NAMES), p=SUB_TYPE_SHARES))]
                sub_accepted = rng.random() < C.SUBSTITUTION_TYPES[sub_type]["accept"]

            cancelled = rng.random() < C.CANCELLED_ORDER_RATE

            for k, i in enumerate(idx):
                items.append(dict(
                    order_id=oid, product_id=sku_ids[i], quantity=int(rng.integers(1, 4)),
                    was_stocked_out=bool(so[k]),
                    was_substituted=bool(so[k] and sub_accepted),
                    # The TYPE is logged. Whether it was any GOOD is not — no
                    # system on earth captures that, which is the whole problem.
                    substitution_type=(sub_type if so[k] and sub_offered else None),
                ))

            orders.append(dict(
                order_id=oid, customer_id=row.customer_id, darkstore_id=store,
                ordered_at_gst=ts_gst, n_items=n_items,
                had_stockout=any_so, had_high_intent_stockout=hi_so,
                substitute_offered=sub_offered, substitute_accepted=sub_accepted,
                substitution_type=sub_type,
                is_cancelled=cancelled, prior_order_count=prior_orders,
            ))

            # ---- will they come back? THE CAUSAL STEP ----
            p_repeat = seg_cfg["base_repeat"]
            if any_so and not is_test:
                tenure = "new" if prior_orders <= C.TENURE_NEW_MAX_PRIOR_ORDERS else "established"
                damage = C.TRUE_EFFECT_PP[tenure] / 100.0
                if hi_so:
                    damage += C.TRUE_HIGH_INTENT_EXTRA_PP / 100.0
                if sub_accepted:
                    # THE UNLOGGED TRUTH: how much of the damage this repairs
                    # depends entirely on the type of swap. The warehouse will
                    # see the type and the acceptance; it will never see this
                    # number. docs/08_ambiguity.md is about recovering it.
                    damage *= (1.0 - C.SUBSTITUTION_TYPES[sub_type]["repair"])
                p_repeat += damage
            p_repeat = float(np.clip(p_repeat, 0.02, 0.97))

            prior_orders += 1
            if not is_test and rng.random() > p_repeat:
                break   # lapsed

            # ---- when? ----
            gap_days = float(rng.exponential(7.0 / max(weekly_rate, 0.05)))
            t = ts_gst + timedelta(days=max(0.25, gap_days))

    return pd.DataFrame(orders), pd.DataFrame(items)


# ---------------------------------------------------------------------------
# 3. SESSIONS + EXPERIMENT
# ---------------------------------------------------------------------------
def gen_sessions_and_experiment(orders: pd.DataFrame):
    """
    App sessions, and the experiment assignment attached to them.

    THE PLANTED BUG: assignment happens at SESSION START; exposure happens at
    CHECKOUT. The treatment adds a pre-approval step, and a slice of treatment
    users abandon on it. So assignment is a clean 50/50 but the CHECKOUT
    population is not — a sample-ratio mismatch created by the product change
    itself, which is the most common and most missed failure mode in real
    experimentation.

    An analyst who only compares converted sessions will read a clean, wrong
    result. The SRM check is what catches it.
    """
    # Every order has a converting session. Plus non-converting browse sessions.
    conv = orders[["order_id", "customer_id", "ordered_at_gst"]].copy()
    conv["session_id"] = ["S" + str(i).zfill(9) for i in range(1, len(conv) + 1)]
    conv["started_at_gst"] = conv["ordered_at_gst"] - pd.to_timedelta(
        rng.integers(120, 1500, len(conv)), unit="s")
    conv["converted"] = True

    # Browse-only sessions: ~1.7 per converting session.
    n_browse = int(len(conv) * 1.7)
    b_cust = rng.choice(orders.customer_id.unique(), n_browse)
    span_s = int((datetime.combine(C.END_DATE, datetime.max.time(), tzinfo=GST) -
                  datetime.combine(C.START_DATE, datetime.min.time(), tzinfo=GST)).total_seconds())
    b_start = [datetime.combine(C.START_DATE, datetime.min.time(), tzinfo=GST) +
               timedelta(seconds=int(s)) for s in rng.integers(0, span_s, n_browse)]
    browse = pd.DataFrame(dict(
        order_id=None, customer_id=b_cust,
        started_at_gst=b_start, ordered_at_gst=pd.NaT,
        session_id=["S" + str(i).zfill(9) for i in range(len(conv) + 1, len(conv) + 1 + n_browse)],
        converted=False,
    ))
    sessions = pd.concat([conv, browse], ignore_index=True)

    # --- assignment, only inside the experiment window ---
    in_win = (sessions.started_at_gst.dt.date >= C.EXPERIMENT_START) & \
             (sessions.started_at_gst.dt.date <= C.EXPERIMENT_END)
    sessions["variant"] = None
    n_in = int(in_win.sum())
    sessions.loc[in_win, "variant"] = rng.choice(
        ["control", "treatment"], n_in, p=[C.EXPERIMENT_INTENDED_SPLIT,
                                           1 - C.EXPERIMENT_INTENDED_SPLIT])

    # --- the SRM: BASKET-DEPENDENT treatment drop-off before checkout ---
    #
    # Pre-approving substitutes for a 20-item basket is 20 decisions. For a
    # 3-item basket it is 3. So abandonment on the new step scales with basket
    # size, and treatment's surviving checkout population skews small-basket.
    #
    # Small baskets have fewer stock-outs by the same (1-p)^n mechanism as the
    # grain trap, and fewer stock-outs means better retention. So the treatment
    # will appear to WIN, decisively, while its true effect is exactly zero.
    #
    # The treatment does not make anyone come back. It makes the people who
    # would have come back anyway more likely to be the ones you measure.
    basket = orders.set_index("order_id").n_items
    sess_basket = sessions.order_id.map(basket).fillna(0)
    p_drop = np.clip(
        C.EXPERIMENT_DROPOFF_BASE + C.EXPERIMENT_DROPOFF_PER_ITEM * sess_basket,
        0.0, 0.85,
    )
    drop = (in_win & (sessions.variant == "treatment") & sessions.converted
            & (rng.random(len(sessions)) < p_drop))
    dropped_orders = set(sessions.loc[drop, "order_id"].dropna())
    sessions.loc[drop, "converted"] = False
    sessions.loc[drop, "order_id"] = None

    # NOTE: no treatment effect is applied to any OUTCOME anywhere. The feature
    # genuinely does nothing (config.TRUE_EXPERIMENT_EFFECT_PP = 0.0). Every
    # difference the naive analysis finds is selection.

    assign = sessions.loc[in_win, ["session_id", "customer_id", "variant", "started_at_gst"]].copy()
    assign = assign.rename(columns={"started_at_gst": "assigned_at_gst"})

    return sessions, assign, dropped_orders


# ---------------------------------------------------------------------------
# 4. DEFECT INJECTION + WRITE
# ---------------------------------------------------------------------------
def to_utc(s: pd.Series) -> pd.Series:
    """Source systems log UTC. The reporting business speaks GST. Hence the bug."""
    return pd.to_datetime(s, utc=True)


def write_all():
    RAW.mkdir(parents=True, exist_ok=True)

    print("  dimensions ...")
    stores = gen_darkstores()
    products = gen_products()
    customers = gen_customers()

    print("  simulating customer order sequences (this is the slow part) ...")
    orders, items = simulate_orders(customers, stores, products)

    print("  sessions + experiment ...")
    sessions, assign, dropped = gen_sessions_and_experiment(orders)
    orders = orders[~orders.order_id.isin(dropped)].copy()
    items = items[items.order_id.isin(set(orders.order_id))].copy()

    # ---- order events, in UTC, with duplicates ----
    print("  injecting defects ...")
    # EVERY order emits order_placed. A cancelled order emits order_placed AND,
    # later, order_cancelled — because it genuinely was placed first. Modelling
    # cancellation as a *substitute* event rather than a *subsequent* one would
    # make cancelled orders disappear from the fact table entirely, and the
    # cancellation rate would read as zero while the money moved. (This was a
    # real bug in an earlier version of this generator, caught by fct_orders
    # returning fewer rows than the source. Kept here as a note because the
    # near-miss is more instructive than the fix.)
    base = orders[["order_id", "customer_id", "darkstore_id", "ordered_at_gst",
                   "is_cancelled"]].copy()
    placed = base.copy()
    placed["event_at_utc"] = to_utc(placed.ordered_at_gst)
    placed["event_type"] = "order_placed"

    canc = base[base.is_cancelled].copy()
    # Cancellations land minutes later, which is exactly why a naive
    # same-timestamp assumption breaks.
    canc["event_at_utc"] = to_utc(canc.ordered_at_gst) + pd.to_timedelta(
        rng.integers(2, 25, len(canc)), unit="m")
    canc["event_type"] = "order_cancelled"

    ev = pd.concat([placed, canc], ignore_index=True)
    ev = ev[["order_id", "customer_id", "darkstore_id", "event_type", "event_at_utc"]]

    # DEFECT: client retry duplicates. Same order_id, same payload, new event row,
    # a few hundred ms later. A naive COUNT(*) overcounts orders by ~1.2%.
    dup_n = int(len(ev) * C.DUPLICATE_ORDER_EVENT_RATE)
    dups = ev.sample(dup_n, random_state=C.SEED).copy()
    dups["event_at_utc"] = dups.event_at_utc + pd.to_timedelta(
        rng.integers(200, 900, dup_n), unit="ms")
    ev = pd.concat([ev, dups], ignore_index=True).sample(frac=1, random_state=C.SEED)

    # ---- fulfilment events: late-arriving ----
    ful = orders[["order_id", "had_stockout", "substitute_offered",
                  "substitute_accepted", "substitution_type", "ordered_at_gst"]].copy()
    ful["fulfilled_at_utc"] = to_utc(ful.ordered_at_gst) + pd.to_timedelta(
        rng.integers(8, 34, len(ful)), unit="m")
    # DEFECT: 8% of rows land in the warehouse up to 6h after the event happened.
    late = rng.random(len(ful)) < C.LATE_ARRIVING_RATE
    ful["ingested_at_utc"] = ful.fulfilled_at_utc + pd.to_timedelta(
        np.where(late, rng.integers(60, C.LATE_ARRIVING_MAX_HOURS * 60, len(ful)),
                 rng.integers(1, 4, len(ful))), unit="m")
    ful = ful[["order_id", "fulfilled_at_utc", "ingested_at_utc", "had_stockout",
               "substitute_offered", "substitute_accepted", "substitution_type"]]

    # ---- write ----
    print("  writing ...")
    customers.drop(columns=["gen_test_truth"]).to_csv(RAW / "raw_customers.csv", index=False)
    products.to_csv(RAW / "raw_products.csv", index=False)
    stores.to_csv(RAW / "raw_darkstores.csv", index=False)
    ev.to_csv(RAW / "raw_order_events.csv", index=False)
    items.to_csv(RAW / "raw_order_items.csv", index=False)
    ful.to_csv(RAW / "raw_fulfilment_events.csv", index=False)

    s_out = sessions[["session_id", "customer_id", "started_at_gst", "converted", "order_id"]].copy()
    s_out["started_at_utc"] = to_utc(s_out.started_at_gst)
    s_out.drop(columns=["started_at_gst"]).to_csv(RAW / "raw_sessions.csv", index=False)

    a_out = assign.copy()
    a_out["assigned_at_utc"] = to_utc(a_out.assigned_at_gst)
    a_out.drop(columns=["assigned_at_gst"]).to_csv(RAW / "raw_experiment_assignments.csv", index=False)

    # The truth file. Written separately, never joined into the warehouse, used
    # only by validate.py to score the analysis. Keeping it out of the warehouse
    # is the point.
    truth = customers[["customer_id", "gen_test_truth"]].rename(
        columns={"gen_test_truth": "is_test_account_truth"})
    truth.to_csv(RAW / "_truth_test_accounts.csv", index=False)

    print(f"\n  customers   {len(customers):>9,}")
    print(f"  products    {len(products):>9,}  (SCD2 rows)")
    print(f"  orders      {len(orders):>9,}")
    print(f"  order items {len(items):>9,}")
    print(f"  order events{len(ev):>9,}  (incl. {dup_n:,} duplicates)")
    print(f"  sessions    {len(sessions):>9,}")
    print(f"  assignments {len(assign):>9,}")


if __name__ == "__main__":
    import os, sys
    os.chdir(Path(__file__).resolve().parents[1])
    sys.path.insert(0, "src")
    print("Generating synthetic q-commerce source systems ...")
    write_all()
    print("\nDone. Raw source files in data/raw/")
