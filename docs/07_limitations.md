# Limitations

*What this project does not establish.*

This file is deliberately near the front of the docs rather than appended to the
back. A limitations section that arrives after the reader has already
screenshotted the number is decoration.

---

## 1. The data is synthetic. This is the limitation that contains the others.

Every figure in this repository comes from `src/generate_data.py`. There is no
talabat data here, no Careem data, no real operator's data of any kind.

**What that means concretely:**

- **94.09% item fill and 66.85% order fill are not measurements.** They are
  properties of a generative process I wrote. Quoting them as a fact about
  quick-commerce would be inventing evidence.
- **The -8.10pp / -2.91pp stock-out effects are recovered injections.** The
  generator put them there. That the analysis found them proves the estimator
  works on this data — nothing more.
- **The magnitudes are invented. The mechanisms are not.** `P(clean) = (1−p)^n`
  is arithmetic; it holds in any warehouse on earth. That stock-outs cluster at
  peak hours, that new stores have untuned assortments, that pickers substitute
  imperfectly — those are structurally real. The *numbers* attached to them are
  mine.

**So what transfers?** The method, the failure modes, and the reasoning. Not the
results. A reader who leaves quoting "one in three q-commerce orders is broken"
has misread this repository, and that is partly my responsibility for making the
number memorable.

### The circularity that cannot be escaped

I wrote the generator **and** the analysis. When `validate.py` reports PASS, it
establishes that my estimator recovers my own assumptions. That is a real and
useful check — a method that fails it is definitely broken — but the asymmetry
is total:

> **Failing validation proves the code is wrong. Passing it does not prove the
> code is right.** It proves the code is not-yet-known-to-be-broken on data whose
> data-generating process is a documented Python file.

Real data has no such file. Real confounders are not a list in `config.py`. The
guard in `analysis.py` (which raises if the causal parameters are reachable) and
the ordering of `validate.py` (which runs only after results are committed to
disk) narrow the ways I can fool myself. They do not eliminate them.

---

## 2. The causal claims are observational

Stock-outs were **not randomised**. They happen because a shelf was empty, and
shelves empty for reasons — peak hours, store age, basket composition — that also
relate to who the customer is.

So the tenure figures in `docs/02_plan.md` are **associations under a stated
adjustment set**, not causal effects. I adjusted for basket size and reported
honestly that it barely moved the estimate. I did not adjust for:

- **Picker behaviour.** Whether a substitute was offered is a human decision,
  correlated with the basket, the hour, and possibly the customer. Unobserved.
- **Category composition.** Beyond the binary high-intent flag, what was *in* the
  basket is not controlled for.
- **Competitive context.** No data on what else was available to that customer at
  that moment.

The experiment in `docs/06_experimentation.md` exists precisely because this
section cannot close. It is what a causal claim would actually require.

---

## 3. Censoring truncates the panel

Retention analysis uses only orders with 30 clear days of follow-up
(`is_observable_30d`). This is correct — the alternative manufactures a fake
cliff — but it has a cost:

- The **final 30 days are excluded** from every retention figure.
- The analysed population **skews toward earlier-acquired customers**, who are
  systematically different: they had more time to form a habit.
- The **newest darkstore (Mirdif, opened mid-window)** contributes almost nothing
  to retention analysis, despite being exactly where the new-store stock-out
  penalty is largest.

That last one is a real gap. The store most likely to be damaging new customers
is the one the analysis can say least about.

---

## 4. The bot detector cannot be perfect, and the metrics say so misleadingly

`int_test_accounts` reports **precision 1.000, recall 0.979**. Both numbers are
honest and both are misleading:

- They exist **only because the data is synthetic** and a ground-truth file
  exists. In production there is no answer key. You would never know your recall.
- The classes **genuinely overlap** — the heaviest human places 31 orders, the
  lightest bot 29. Recall is capped below 1.0 by the world, not by tuning.
- **Volume is the weakest possible signal** and the only one this dataset carries.
  A real detector would triangulate on internal IP ranges, `@company` email
  domains, shared device fingerprints, accounts created in one afternoon, or a
  payment instrument repeated across "customers". None of that exists here.

Reporting precision/recall on a production bot detector would be a category
error. It is reported here because here, uniquely, it is checkable.

---

## 5. The substitution question is unanswerable, not merely hard

Covered fully in `docs/08_ambiguity.md`. Restated because it is the limitation
most likely to be skimmed:

**No source system records whether a customer was okay with a substitution.** Not
imperfectly — *not at all*. Three defensible proxies disagree by 4.6pp. The
ranking is stable and the magnitude is not, so the magnitude is not reportable.

No amount of modelling recovers a label that was never captured. The fix is a
one-question survey, not a cleverer estimator.

---

## 6. Scope: what a real version would have and this does not

Stated so nobody has to guess whether the omissions were decisions or oversights:

| Missing | Why it matters | Why it is absent |
|---|---|---|
| **Cost data** | Every recommendation implies a spend. Without unit economics, "improve fill rate for new customers" has no price tag. | Would require inventing a cost model — the one thing this project refuses to do. The memo handles this with stated assumptions and sensitivity instead. |
| **Rider / delivery-time data** | Late delivery is plausibly a bigger retention driver than stock-outs. | Out of scope; would double the model. Its absence means stock-out effects here may absorb variance that belongs to lateness. |
| **Price & promotion history** | Confounds retention heavily. | Not modelled. A real analysis could not omit this. |
| **Competitive data** | The counterfactual is "they ordered from someone else". | Nobody has this. |
| **Incremental models** | 1.1M rows full-refresh in seconds; billions would not. | Documented in `docs/03_data_model.md` rather than built, since DuckDB makes it unnecessary and pretending otherwise would be theatre. |

The rider-data omission is the most consequential. If delivery lateness
correlates with stock-outs — and operationally it does, both spike at peak — then
some of the effect attributed here to stock-outs belongs to lateness. **The
estimates in this repo are plausibly upward-biased for that reason**, and nothing
in the data can separate them.

---

## 7. One reviewer, one author

No peer review, no second pair of eyes on the SQL, no adversarial reading of the
analysis. Every dbt test was written by the person whose code it tests, which is
a well-known way to write tests that pass.

The mistakes documented in this repo — the cancelled-order bug, the bot
threshold, the dead constant, the doc-drift checker that could not fail — were
all caught by me, eventually, usually after they had been wrong for a while.
The interesting question is what is still in here that I have not noticed.

---

## The honest summary

This project demonstrates **how to reason about a warehouse and an ambiguous
question**. It does not demonstrate anything about quick commerce that a reader
should carry away as fact.

If it changes how someone thinks about the gap between an ops metric and a
customer metric, it has done its job. If someone quotes 66.85% in a meeting, it
has done harm, and the fault is partly mine for making it quotable.
