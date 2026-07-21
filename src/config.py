"""
config.py — the single source of truth for how the synthetic world is built.

WHY THIS FILE EXISTS
--------------------
This project makes a causal claim: "a stock-out costs you a measurable amount of
future retention, and the naive comparison gets that number wrong."

On real observational data you can never prove an estimator recovered the truth,
because you never see the truth. On synthetic data you can — but only if the
ground truth is declared up front, in one place, before any analysis runs.

So every number the generator injects lives here, is referenced by the docs, and
is compared against the analysis output in `reports/results.json`. If the
analysis recovers these values, the method works. If it does not, the project
says so rather than quietly tuning until it does.

READ THIS AS THE ANSWER KEY. The analysis code never imports the causal
parameters (only `generate_data.py` does) — see the guard at the bottom.

Data is SYNTHETIC. It is not talabat data, Careem data, or any real operator's
data. The generating process below is a deliberate caricature of quick-commerce
mechanics informed by public reporting on the sector; it is designed to be
*structurally* realistic (grains, latencies, defects), not to predict any real
company's numbers.
"""

from datetime import date

# ---------------------------------------------------------------------------
# 1. WORLD SHAPE
# ---------------------------------------------------------------------------
# A 90-day window is the shortest span that still lets us measure a 30-day
# retention outcome with a 60-day exposure window. Shorter, and every customer
# acquired in the back half is censored.
SEED = 20260715
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 3, 31)          # inclusive
RETENTION_WINDOW_DAYS = 30            # outcome horizon after the focal order
EXPOSURE_CUTOFF_DAYS = 60             # focal orders must leave 30 clear days

N_CUSTOMERS = 40_000
N_PRODUCTS = 2_500                    # a real darkstore carries ~2-4k SKUs

# Dubai darkstores. Catchment radius drives delivery time; affluence drives
# basket. These are invented, not scraped.
DARKSTORES = [
    # (id,   name,            area,           affluence, opened_on)
    ("DS01", "Marina",        "Dubai Marina", 1.25, date(2025, 3, 1)),
    ("DS02", "JLT",           "JLT",          1.10, date(2025, 4, 1)),
    ("DS03", "Business Bay",  "Business Bay", 1.20, date(2025, 6, 1)),
    ("DS04", "Deira",         "Deira",        0.80, date(2025, 8, 1)),
    ("DS05", "Al Barsha",     "Al Barsha",    1.00, date(2025, 11, 1)),
    ("DS06", "Mirdif",        "Mirdif",       0.90, date(2026, 1, 15)),  # opens mid-window
]

CATEGORIES = [
    "Fresh Produce", "Dairy & Eggs", "Bakery", "Meat & Poultry", "Frozen",
    "Beverages", "Snacks", "Pantry", "Household", "Personal Care",
    "Baby", "Pet",
]

# Categories whose stock-outs hurt most. A missing bag of crisps is an
# annoyance; missing infant formula or fresh milk is why the customer opened
# the app at 11pm. This asymmetry is the whole reason a flat fill-rate target
# is the wrong tool — and the analysis is built to surface it.
HIGH_INTENT_CATEGORIES = {"Dairy & Eggs", "Fresh Produce", "Baby", "Meat & Poultry"}

# ---------------------------------------------------------------------------
# 2. CUSTOMER SEGMENTS  (assigned at acquisition, drive behaviour)
# ---------------------------------------------------------------------------
# share, base weekly order rate, price sensitivity, base 30d repeat prob
# NOTE ON base_repeat: this is the per-order probability the customer places
# ANOTHER order, so expected lifetime orders = 1/(1-base_repeat), further
# truncated by the 90-day window. These values were set so the simulated
# order-per-customer distribution lands in a plausible q-commerce range rather
# than to hit any particular headline order count.
SEGMENTS = {
    "Weekly Stock-Up":   dict(share=0.22, weekly_rate=1.1, basket_mult=1.85, base_repeat=0.80),
    "Top-Up Regular":    dict(share=0.31, weekly_rate=2.4, basket_mult=0.70, base_repeat=0.86),
    "Late-Night Rescue": dict(share=0.18, weekly_rate=0.9, basket_mult=0.55, base_repeat=0.60),
    "Occasional":        dict(share=0.29, weekly_rate=0.3, basket_mult=1.00, base_repeat=0.36),
}

# ---------------------------------------------------------------------------
# 3. THE CAUSAL GROUND TRUTH  ← the answer key
# ---------------------------------------------------------------------------
# A stock-out on a focal order reduces the probability that the customer orders
# again within 30 days. The effect is NOT uniform — that is the finding.
#
# Tenure is what moderates it. A stock-out on order #1 is evidence the service
# does not work. A stock-out on order #30 is a Tuesday. The customer has a prior
# built from 29 orders that went fine; one miss barely moves it.
#
# Units are absolute percentage points on the 30-day repeat probability.
TRUE_EFFECT_PP = {
    "new":         -9.0,   # <= 2 prior orders
    "established": -1.5,   # >  2 prior orders
}
TENURE_NEW_MAX_PRIOR_ORDERS = 2

# Additional damage when the stocked-out item was high-intent (the reason for
# the trip), applied on top of the tenure effect.
TRUE_HIGH_INTENT_EXTRA_PP = -4.0

# Substitution repairs part of the damage — but only part, only if the customer
# accepts, and by an amount that depends on the TYPE (see SUBSTITUTION_TYPES).
# This is why "offer a substitute" is not a free fix, and why "substitution
# rate" as a KPI is close to meaningless without type.

# ---------------------------------------------------------------------------
# 4. THE CONFOUNDER  ← why the naive estimate will be wrong
# ---------------------------------------------------------------------------
# Heavy users order more often, so they are mechanically more likely to have hit
# a stock-out at some point. They also retain better *for reasons that have
# nothing to do with stock-outs* (habit, wallet share, basket routine).
#
# So in a naive "stocked-out vs not" comparison, the stocked-out group is
# over-weighted with heavy users, whose high baseline retention MASKS the
# damage. The naive estimate is biased TOWARD ZERO — it will report that
# stock-outs barely matter, or even help.
#
# This is the opposite of the usual intuition and it is why the project exists:
# the confound does not exaggerate the problem, it hides it.
#
# No knob is needed here. The bias emerges from the generative structure:
# order frequency drives both exposure and baseline retention. That is a
# stronger demonstration than injecting a bias term by hand, because the
# analysis has to contend with a confound that arises the way real ones do.

# ---------------------------------------------------------------------------
# 5. STOCK-OUT MECHANICS
# ---------------------------------------------------------------------------
BASE_STOCKOUT_RATE = 0.031        # per item, per order, before modifiers
STOCKOUT_PEAK_MULT = 2.3          # 19:00-23:00 GST — the dinner rush drains shelves
STOCKOUT_LATE_NIGHT_MULT = 3.1    # 00:00-04:00 GST — nothing has been restocked yet
STOCKOUT_NEW_STORE_MULT = 1.8     # a store <45 days old has not tuned its assortment
STOCKOUT_NEW_STORE_DAYS = 45
SUBSTITUTION_OFFER_RATE = 0.62    # picker offers a substitute this often

# --- Substitution TYPES ---------------------------------------------------
# A picker facing an empty shelf has three moves, and they are not equivalent.
# Swapping 1L milk for 2L of the same brand is a near-perfect save. Swapping
# Almarai milk for Al Rawabi is a real but smaller save. Swapping milk for
# laban because "it's also dairy" is the move that loses the customer.
#
# THE CRITICAL POINT FOR docs/08_ambiguity.md:
# The `repair` values below are GROUND TRUTH THAT THE SOURCE DATA NEVER
# RECORDS. No system logs "was this substitution any good?" — there is no
# satisfaction field, no thumbs-up, no label. The warehouse knows only the
# TYPE and whether it was ACCEPTED. Recovering quality from that is the
# ambiguous question, and it is the point of the exercise.
#
# offer_share : given a substitute is offered, how often it is of this type
# accept      : P(customer accepts | offered this type)
# repair      : fraction of stock-out damage undone IF accepted  <- NEVER LOGGED
SUBSTITUTION_TYPES = {
    "same_brand_diff_size":   dict(offer_share=0.34, accept=0.78, repair=0.82),
    "diff_brand_same_product":dict(offer_share=0.41, accept=0.55, repair=0.47),
    "diff_product_same_cat":  dict(offer_share=0.25, accept=0.29, repair=0.11),
}
# Sanity: offer_share must sum to 1.0. Asserted in generate_data.py rather than
# trusted, because a silent renormalisation would corrupt the answer key.

# ---------------------------------------------------------------------------
# 6. THE EXPERIMENT  (pre-approved substitutions)
# ---------------------------------------------------------------------------
# Treatment: at checkout, let the customer pre-approve a substitute per item.
# Hypothesis: pre-approval converts a refund into a delivery, so it should
# recover part of the stock-out damage.
# WINDOW CHOICE: the experiment must END at least RETENTION_WINDOW_DAYS before
# the data does, or its own primary metric is unobservable. A first draft of
# this project ran the experiment 1-31 March against data ending 31 March, and
# only 1,555 of 32,591 converted sessions had an evaluable 30-day outcome. The
# test could not answer the question it was built to ask.
#
# This is not a synthetic-data artefact. Running an experiment whose primary
# metric needs a longer horizon than the readout allows is routine, and it is
# usually discovered at the readout meeting.
EXPERIMENT_START = date(2026, 1, 20)
EXPERIMENT_END = date(2026, 2, 20)   # ends 39 days before data ends: 30d outcome observable
EXPERIMENT_INTENDED_SPLIT = 0.50

# THE TRUE TREATMENT EFFECT IS EXACTLY ZERO.
#
# This is deliberate and it is the point. Pre-approval changes nothing about
# whether the customer comes back — the feature does not work.
#
# The naive analysis will nonetheless report a large, significant, positive
# effect. Not because of noise, and not because of p-hacking: because the
# treatment SELECTS ITS OWN ANALYSIS POPULATION (see the drop-off below). The
# fake win survives any amount of statistical sophistication applied downstream,
# because the damage was done before the statistics started.
#
# A demonstration where the treatment genuinely worked would teach nothing. The
# only way to show that an SRM check earns its keep is to build an experiment
# that looks like a winner and is not.
TRUE_EXPERIMENT_EFFECT_PP = 0.0

# --- The SRM bug, deliberately planted ------------------------------------
# Assignment is written at SESSION START. Exposure only happens at CHECKOUT.
# The treatment UI adds a pre-approval step, and some treatment sessions abandon
# on it. So the ANALYSED population (checkout sessions) is no longer 50/50 even
# though ASSIGNMENT was.
#
# THE CRITICAL DETAIL: the drop-off is NOT random. Pre-approving substitutes for
# a 20-item basket is 20 decisions; for a 3-item basket it is 3. So abandonment
# rises with basket size, and the treatment's surviving checkout population is
# systematically SMALLER-BASKETED than control's.
#
# Small baskets have fewer stock-outs (P(clean) = (1-p)^n — the same mechanism as
# the grain trap). Fewer stock-outs means higher retention. So treatment looks
# like it WINS, by a wide and highly significant margin, while doing nothing.
#
# This is not an exotic failure. It is the ordinary one: any treatment that
# changes the funnel changes who reaches the end of it, and comparing the
# survivors compares populations the treatment itself selected. No CUPED, no
# stratification, no larger sample recovers from it — the randomisation is gone.
EXPERIMENT_DROPOFF_BASE = 0.010          # baseline abandonment on the new step
EXPERIMENT_DROPOFF_PER_ITEM = 0.022      # each extra item to approve adds friction

# ---------------------------------------------------------------------------
# 7. DATA DEFECTS  (the "real world" tax)
# ---------------------------------------------------------------------------
# Each of these is a defect a working analyst hits in their first month on a
# real event pipeline. Each has a dbt test written against it.
DUPLICATE_ORDER_EVENT_RATE = 0.012      # client retries without idempotency key
LATE_ARRIVING_MAX_HOURS = 6             # fulfilment events trickle in
LATE_ARRIVING_RATE = 0.08
MISSING_CATEGORY_RATE = 0.030           # catalogue join failures
TEST_ACCOUNT_COUNT = 47                 # internal QA accounts, ~100% conversion
TEST_ACCOUNT_ORDER_MULT = 22            # they hammer the system
CANCELLED_ORDER_RATE = 0.024

REPORTING_TZ = "Asia/Dubai"             # GST, UTC+4 — no DST
LOGGING_TZ = "UTC"                      # events land in UTC. The 4h gap is the bug.

# ---------------------------------------------------------------------------
# GUARD: the analysis must not peek at the answer key.
# ---------------------------------------------------------------------------
# `analysis.py` asserts that it has not imported the causal parameters. This is
# enforced mechanically rather than by good intentions, because "I promise I
# didn't look" is not a methodology.
CAUSAL_PARAMS = (
    "TRUE_EFFECT_PP",
    "TRUE_HIGH_INTENT_EXTRA_PP",
    "SUBSTITUTION_TYPES",              # the `repair` key is the unlogged truth
    "TRUE_EXPERIMENT_EFFECT_PP",
    "EXPERIMENT_DROPOFF_BASE",
    "EXPERIMENT_DROPOFF_PER_ITEM",
)
