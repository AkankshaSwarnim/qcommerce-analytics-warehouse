# The business, before the data

*Why a stock-out in quick commerce is not the same event as a stock-out anywhere
else.*

---

## A disclosure, because it shapes everything below

I spent 2014–15 running customer experience at an on-demand grocery startup in
India, from launch through 20,000+ orders a day across 20 cities. **Every
stock-out in this project is one I have personally apologised for.**

That is why this repository exists, and it is also its main bias. I chose
stock-outs as the subject because I know that problem in my hands, not because I
proved it was the most valuable question available. Someone with rider-ops
experience would have built the delivery-lateness version of this repo and might
have been more right. See `docs/07_limitations.md`.

---

## What quick commerce actually is

Not "groceries, but faster." The promise — 10 to 20 minutes — forces a different
business, and every constraint below falls out of that one number.

| | Supermarket | E-grocery (next-day) | **Quick commerce** |
|---|---|---|---|
| Promise | you drive there | tomorrow, 2h slot | **~15 minutes** |
| Assortment | 30,000+ SKUs | 20,000+ | **2,000–4,000** |
| Fulfilment | customer picks | regional warehouse | **darkstore, ~2km** |
| Basket | large, planned | large, planned | **small, urgent** |
| Substitution | customer decides | customer pre-approves | **picker decides, now** |

The middle row is the one that matters. **A darkstore is small on purpose** —
close enough to reach you in 15 minutes means expensive urban space, which means
a few thousand square feet, which means 2,000–4,000 SKUs where a supermarket
holds 30,000.

So the assortment is thin by design. **Stock-outs are not a failure of the model.
They are the model.** You cannot inventory your way out of them without buying
space that destroys the unit economics — the constraint the promise created.

---

## The darkstore

```
        ~2km catchment
    ┌─────────────────────┐
    │   2,000-4,000 SKUs  │   thin assortment: no room for depth
    │   ~2,500 sq ft      │   urban rent: the binding cost
    │   pickers on shift  │   labour scales with orders, not revenue
    └──────────┬──────────┘
               │  15 min promise
               ▼
          the customer
```

Three consequences the data has to respect:

1. **Depth is sacrificed for breadth.** One brand of milk, not nine. When it goes,
   there is no second-best on the shelf — only a different product.
2. **Restocking is a shift, not a moment.** Shelves drain across the evening and
   are refilled overnight. Stock-out risk is a **function of the hour**, and the
   generator models it that way: peak dinner ×2.3, late night ×3.1.
3. **A new store has not learned its neighbourhood yet.** Assortment is a guess
   for the first weeks. Modelled as ×1.8 for stores under 45 days old — and the
   newest store in this dataset opens mid-window, which is exactly where the
   analysis can say least. That is not a coincidence; it is the censoring
   problem biting where it hurts most.

---

## The unit economics, and why "just improve fill rate" is not advice

Roughly, per order:

```
  basket value          AED 45-80
    − COGS                          the groceries
    − picking labour                scales with items, not value
    − rider cost                    scales with distance, not value
    − packaging
  ──────────────────
  contribution          thin. often negative on small baskets.
```

Two facts collide:

- **Cost scales with items and distance. Revenue scales with basket value.** A
  3-item late-night rescue order can cost more to deliver than it earns.
- **The fix for stock-outs is inventory. The constraint is space.** Every extra
  SKU you stock to raise fill rate is space, working capital, and waste — on
  fresh categories, literal spoilage.

This is why "improve fill rate" is not a recommendation. It is a wish. **Fill
rate is bought, not decided**, and the currency is the one thing a darkstore has
none of. Any honest recommendation has to say *which* fill rate, for *whom*, and
what it displaces — which is the entire argument of `docs/02_plan.md`.

---

## The four customers, and why they are not one customer

The generator models four segments because they behave differently enough that
averaging them destroys the signal:

| Segment | Basket | Rhythm | Why they opened the app |
|---|---|---|---|
| **Weekly Stock-Up** | ~15 items | weekly | replacing a supermarket trip |
| **Top-Up Regular** | ~6 items | 2-3×/week | ran out of two things |
| **Late-Night Rescue** | ~4 items | sporadic | **the shops are shut** |
| **Occasional** | ~8 items | rare | tried it once |

Read the basket column against `docs/02_plan.md`. **Weekly Stock-Up buys ~15
items, so they hit a stock-out roughly every other order** — mechanically, not
because anyone served them badly. They are simultaneously the highest-value
segment and the worst-served, and no item-level metric can see it.

Late-Night Rescue is the segment that explains the timezone bug mattering. They
order 00:00–04:00 GST, which is 20:00–00:00 UTC **the previous day**. Report on
raw UTC dates and an entire segment's behaviour lands on the wrong day —
**14.2% of all orders** in this dataset.

---

## Why the missing item's identity matters

A stock-out is not one event. It is at least two:

- **Missing crisps.** Annoying. The order still worked.
- **Missing infant formula at 11pm.** This is not a missing item. This is *the
  reason the app was opened*, and the service just failed at its only job.

Quick commerce lives on urgency. The whole promise is "the thing you need, now."
When the thing you need is the thing that is missing, the promise did not
under-deliver — it broke.

`fct_order_items.is_high_intent_category` flags Dairy & Eggs, Fresh Produce,
Baby, and Meat & Poultry. **That list is a judgement, not a measurement**
(`docs/05_metrics.md` says so where it is defined), and it exists because a flat
fill-rate target cannot express the difference between an annoyance and a broken
promise.

---

## The substitution decision, as it actually happens

A picker is standing in front of an empty shelf. There is a rider outside. The
clock is at four minutes. They have three options and about ten seconds:

| Option | What the customer sees |
|---|---|
| **Same brand, different size** | 2L instead of 1L. Barely notices. |
| **Different brand, same product** | Al Rawabi instead of Almarai. Notices. Mostly fine. |
| **Different product, same category** | Laban instead of milk. **This is not milk.** |
| **Refund the line** | Order arrives incomplete. |

These are not equivalent, and `docs/08_ambiguity.md` shows the data agrees: the
best swap recovers meaningfully, **the worst is statistically indistinguishable
from offering nothing at all.**

Nobody logs which one happened *and whether it worked*. The type is recorded.
The customer's reaction is not. That absence is the subject of the ambiguity
chapter, and it is not a data-engineering oversight — **there is no field to fill
in, because nobody ever asked the customer.**

---

## The question this project answers

> *"Why is retention falling when our fill rate has stayed above 95%?"*

Everything above is why that question is hard:

- stock-outs are **structural**, not a bug to be fixed;
- the metric measuring them is **an ops metric being read as a customer metric**;
- the customers hit hardest are the **most valuable ones**, mechanically;
- the obvious fix (**more inventory**) is the one the model forbids;
- and the obvious mitigation (**substitute it**) is unmeasured.

The warehouse exists to connect a missing item at 19:04 on a Tuesday to a
customer who quietly stopped ordering in March. Nothing in any single source
system can do that.

→ [`docs/02_plan.md`](02_plan.md)
