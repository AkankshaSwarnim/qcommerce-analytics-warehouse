# Memo: where to spend the fill-rate budget

**To:** VP Operations, VP Product
**From:** Data Science
**Re:** "Why is retention falling when fill rate is above 95%?"
**Length:** one page. Evidence in `docs/`. Assumptions stated, not buried.

---

## The answer to your question

**Fill rate never dropped. You were reading a true number that cannot answer the
question you asked.**

| | |
|---|---|
| Item fill rate — what the shift report shows | **94.09%** |
| Order fill rate — what the customer experiences | **66.85%** |

Same 135,996 orders, same 1,054,890 items, **27.2 points apart**. An order is
clean only if every item is, so at a 5.9% miss rate and a 7.8-item
basket, **one in three orders is broken by arithmetic.**

**This is not an ops failure.** Nobody is doing their job badly. The metric is
measuring items; the customer is buying baskets.

---

## The part that should worry you

| Basket size | Item fill | Order fill |
|---|---|---|
| 1-3 | 93.78% | **85.85%** |
| 4-6 | 93.74% | **73.27%** |
| 7-10 | 94.06% | **62.75%** |
| 11-15 | 94.70% | **52.69%** |
| 16+ | 95.09% | **43.56%** |

Item fill says large baskets are served **better**. Order fill says **twice as
badly**. Large baskets are Weekly Stock-Up — our highest-value segment.

**Our headline metric conceals that our best customers get our worst experience**,
and it does so more the more they spend with us.

---

## What a broken order costs

| Customer | Effect on 30-day repeat |
|---|---|
| **New** (≤2 prior orders) | **-8.10 pp** |
| Established | -2.91 pp |

**2.8× more damage on a first basket.** A stock-out on order #1 is evidence
the service does not work. On order #30 it is a Tuesday — they have 29 orders'
worth of prior saying we are fine.

New customers are **68%** of the orders we can measure.

The pooled figure (-7.04 pp) averages two populations that need opposite
decisions. **Do not put it on a dashboard.**

---

## Recommendation

**1. Change the headline metric.** Report order fill rate. Keep item fill for
shift management — it is the right ops metric — but stop letting it answer
customer questions. *Cost: nothing. Do it this week.*

**2. Protect first baskets.** Weight assortment depth and picker priority toward
new-customer orders, where damage is 2.8× larger. *Cost: real. See below.*

**3. Stop offering same-category substitutes.** Milk → laban recovers nothing
measurable: the confidence interval spans zero under every proxy we tested
(`docs/08_ambiguity.md`). Roughly a quarter of substitution offers are ritual —
picker time spent on nothing. *Cost: negative. This frees capacity.*

**4. Do not ship pre-approved substitutions.** It destroys **18.9% of
conversions** in its arm and buys no measurable retention
(`docs/06_experimentation.md`). The idea is sound; the checkout interstitial is
what kills it. Move it out of the purchase path and re-test.

**5. Ask the customer.** A one-question post-delivery survey on substituted
orders — *"was this replacement okay?"* — would replace three disagreeing proxies
with an actual label. *Cost: trivial. Should have existed before the dashboard
did.*

---

## What I cannot tell you, and will not pretend to

**We have no cost data in the warehouse.** So I cannot tell you whether to spend
AED 3M on inventory versus picker training versus substitutions. Any ROI number
I produced would be a cost model I invented, dressed as a finding.

What I can do is show you **what would have to be true** for recommendation 2 to
pay:

### Break-even, under stated assumptions

*Assumptions — all of them arguable, none of them measured here:*

- New-customer 12-month value: **AED 400** *(if it is 200, halve everything below)*
- New customers acquired per month: **5,000**
- Share whose first basket hits a stock-out: **34.8%** *(from our data)*
- Retention damage on those: **-8.10 pp** *(from our data)*

*Then:*

```
customers lost to a first-order stock-out
  = 5,000 × 34.8% × 8.1%   ≈  ~141 / month
value at risk
  = ~141 × AED 400          ≈  AED 56k / month
                                ≈ AED 680k / year
```

**So the fill-rate intervention for new customers is worth doing if it costs less
than ~AED 680k/year and works perfectly.** It will not work perfectly. At a
50% effectiveness assumption: **~AED 340k/year.**

### What changes my mind

| If this assumption is wrong | The case |
|---|---|
| New-customer value is AED 200, not 400 | **halves** — marginal |
| Effectiveness is 25%, not 50% | **halves again** — do not fund it |
| Delivery lateness (not stock-outs) drives the damage | **collapses** — we are treating a symptom |

That last row is the real risk, and I want it on the record: **we have no rider
data in this warehouse.** Lateness and stock-outs both spike at peak hours, so
some of the effect I have attributed to stock-outs may belong to lateness. I
cannot separate them with the data we have. **Get me rider timestamps and this
memo may change.**

---

## What I need

1. **Rider / delivery-time data** in the warehouse. The largest known threat to
   everything above.
2. **A decision on who owns order fill rate.** Ops owns the lever, Product owns
   the outcome. Right now nobody owns it, which is why nobody reported it.
3. **Sign-off on the survey.** One question. It closes the ambiguity chapter
   permanently and costs less than this memo did.

---

*Data is synthetic — see `docs/07_limitations.md`. The magnitudes above are
properties of a generative model, not measurements of this business. The
mechanisms are real; the numbers are illustrative.*
