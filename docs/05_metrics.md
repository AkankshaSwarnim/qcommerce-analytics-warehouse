# Metric definitions

*Not a dashboard. A contract.*

A metric without a written definition is not a metric — it is a number that two
people will compute differently and then argue about in a meeting neither of them
enjoys. This file is the thing that stops that argument, and it is the reason two
dashboards agree.

Each entry answers seven questions: what it is, how it is computed, why anyone
cares, what it hides, who owns it, when it breaks, and how it is usually got
wrong.

---

## 1. Item fill rate

| | |
|---|---|
| **Definition** | Share of ordered items that were actually delivered. |
| **Formula** | `1 − (stocked_out_items / total_items)` |
| **Grain** | order-item, rolled to any level |
| **Source** | `fct_order_items.was_stocked_out` |
| **Owner** | Warehouse Operations |

**Why it exists:** it measures the thing ops controls. A picker cannot control
basket size; they can control whether the shelf was stocked. As an *operational*
metric it is correct and useful.

**What it hides:** the customer. It is an average over items, and nobody buys an
item — they buy a basket. See metric 2, and see `docs/02_plan.md` for the 27pp
consequence.

**When it breaks:**
- **On the current day.** ~8% of fulfilment rows arrive up to 6h late, so today's
  figure is provisional and will move overnight. Read `is_late_arriving` before
  trusting a same-day number.
- **When quoted per customer.** Large-basket customers hit more stock-outs
  mechanically. A per-customer rate ranks your best customers as worst-served.

**Common mistake:** reporting this as *the* fill rate. It is the ops fill rate.
Saying "fill rate is 94%" to a product audience is technically true and
practically a lie.

---

## 2. Order fill rate  ⭐

| | |
|---|---|
| **Definition** | Share of orders where **every** item was delivered. |
| **Formula** | `clean_orders / total_orders`, clean = no stocked-out item |
| **Grain** | order |
| **Source** | `fct_orders.is_clean_order` |
| **Owner** | **Product** (contested — see below) |

**Why it exists:** it is what the customer experiences. They do not experience
94% of a basket; they experience "my order was wrong."

**The relationship to metric 1** is not a nuance, it is the finding:

```
P(clean order) ≈ (1 − item_miss_rate) ^ basket_size
```

Both metrics are correct. They diverge by ~27pp and they support opposite
decisions. The invariant `order_fill ≤ item_fill` always holds and is enforced by
`dbt/tests/assert_order_fill_never_exceeds_item_fill.sql`.

**What it hides:** severity. A missing bag of crisps and missing infant formula
both make an order "unclean". See metric 6.

**Ownership is contested, and that is the point.** Ops owns the *lever*; Product
owns the *outcome*. If Ops owns this metric they will be measured on basket size
they do not control. If nobody owns it, it does not get reported — which is the
status quo this project exists to change.

**When it breaks:** cancelled orders. Excluded from the denominator here (nothing
was picked, so nothing was missing), but Finance counts them. Two correct answers
to "how many orders yesterday?" — hence this file.

---

## 3. 30-day repeat rate

| | |
|---|---|
| **Definition** | Share of focal orders followed by another order from the same customer within 30 days. |
| **Formula** | `days_to_next_order <= 30`, over orders with `is_observable_30d` |
| **Grain** | order (**not** customer) |
| **Source** | `fct_customer_orders.repeat_within_30d` |
| **Owner** | Product / Growth |

**Why order-grain and not customer-grain:** the question is "did *this
experience* cost us the next order", which is an order-level question. A
customer-level retention rate cannot attribute anything to a specific order.

**When it breaks — and this is the one that lies:**

> **Censoring.** An order placed 5 days before the data ends *cannot* have a
> 30-day outcome. Counting it as "did not repeat" is not conservative — it is
> wrong. It mislabels every recent order as a failure and manufactures a
> retention cliff at the end of every chart.

The cliff lies in the *alarming* direction, which is precisely how it survives
review: **nobody interrogates a number that makes them worried.**

`is_observable_30d` marks orders with 30 clear days behind them. Everything else
is **excluded**, never defaulted to false. Enforced by
`dbt/tests/assert_retention_outcome_not_censored.sql`.

**Common mistakes:**
- `COUNT(*)` over all orders, including censored ones → fake cliff.
- Including QA bots → they never lapse, so they inflate it. Filter
  `is_test_account`.
- Reading it as causal. It is downstream of price, habit, weather, and a
  competitor's promo. One stock-out is a whisper in a stadium.

---

## 4. Conversion rate

| | |
|---|---|
| **Definition** | Share of sessions that resulted in a placed order. |
| **Formula** | `converted_sessions / total_sessions` |
| **Grain** | session |
| **Source** | `fct_sessions.converted` |
| **Owner** | Product |

**Why it is in this file at all:** because `docs/06_experimentation.md` is a story
about a feature that destroyed 19% of conversions while the primary metric
reported "no effect". Conversion is the guardrail that would have caught it on
day two.

**When it breaks:** any metric computed *among converters* is blind to changes in
conversion itself. If a treatment moves this number, every downstream
per-converter metric is comparing populations the treatment selected.

**Common mistake:** treating it as a guardrail you check if you remember. Any
experiment touching the funnel must have it as a **required** guardrail, not an
optional one.

---

## 5. Substitution rate

| | |
|---|---|
| **Definition** | Share of stock-outs where a substitute was offered. |
| **Formula** | `substitute_offered / stocked_out_orders` |
| **Grain** | order |
| **Owner** | Warehouse Operations |

**This metric is close to meaningless on its own**, and it is documented here
mainly to say so.

`docs/08_ambiguity.md` shows the three swap types are not equivalent: the best
recovers ~6pp of retention, the worst is **statistically indistinguishable from
offering nothing** (CI spans zero under both proxies). A single "substitution
rate" averages a real intervention with a ritual one.

**If you must report it, report it by type.** A rising substitution rate driven by
same-category swaps is not an improvement; it is picker time being spent on
nothing.

**What it cannot tell you:** whether the substitution was any *good*. Nothing in
any source system records that. See `docs/08_ambiguity.md`.

---

## 6. High-intent stock-out rate

| | |
|---|---|
| **Definition** | Share of orders with a stock-out in a high-intent category. |
| **Formula** | `had_high_intent_stockout / total_orders` |
| **Categories** | Dairy & Eggs, Fresh Produce, Baby, Meat & Poultry |
| **Grain** | order |
| **Source** | `fct_orders.had_high_intent_stockout` |
| **Owner** | Product, with Category input |

**Why it exists:** a missing bag of crisps is an annoyance. Missing infant formula
is why the customer opened the app at 11pm. Order fill rate treats these
identically; the retention damage does not.

**The honest caveat:** the category list is a **judgement**, not a measurement.
It was chosen on domain reasoning, not derived from data, and it is defined in
one place (`fct_order_items.is_high_intent_category`) so it can be argued with
rather than silently re-derived by every analyst.

**When it breaks:** if the category list drifts from reality — a new category
launches, or "Baby" splits into formula and toys — this metric silently changes
meaning while the name stays the same. Review it quarterly or it becomes a lie
with a good reputation.

---

## 7. Ingestion lag

| | |
|---|---|
| **Definition** | Minutes between an event happening and the warehouse seeing it. |
| **Formula** | `ingested_at_utc − fulfilled_at_utc` |
| **Grain** | order |
| **Source** | `fct_orders.ingestion_lag_minutes` |
| **Owner** | Data Platform |

**Why a data-quality metric is in a business metric file:** because every metric
above is wrong on the current day and nobody knows unless this is visible. ~8% of
fulfilment rows trail by up to 6 hours.

This cannot be fixed in SQL — the data genuinely was not there. What SQL can do
is make the latency **visible** so consumers stop pretending today's number is
final. The fix is to mark the day provisional, not to argue with physics.

---

## Conventions that apply to everything here

1. **All dates are GST.** Every source logs UTC. The conversion happens exactly
   once, in staging, driven by `vars.reporting_tz`. **14.2% of orders land on a
   different day** under UTC than GST — the late-night rush is an entire segment
   that moves.
2. **QA bots are excluded from every analysis**, never deleted. Finance needs raw
   counts to reconcile against the payment processor. The contract is: flagged in
   `dim_customer.is_test_account`, filtered by every consumer.
3. **NULL categories become `'Unmapped'`**, never filtered. A quiet
   `WHERE category IS NOT NULL` deletes 3% of revenue from every category report
   and makes totals stop tying out. An `Unmapped` bucket stays visible and
   embarrasses someone into fixing the catalogue.
4. **Cancelled orders** are in `fct_orders` for Finance and out of
   `int_customer_order_sequence` for behaviour. A cancelled order is not an
   experience of the service — nothing was picked, nothing was missing.
