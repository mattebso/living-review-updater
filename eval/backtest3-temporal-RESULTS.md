# Temporal backtest results — 2026-07-31

## Why this test exists

The gate-passing backtest (`backtest-RESULTS.md`, 2026-07-24) used a **random**
stratified 80/20 split and reported median **WSS@95 ≈ 84%** across 26 SYNERGY
reviews. That number went into the public README. But a real living-review
update is not a random sample: the team has screened everything published up to
a date, and the update delivers records published **after** it. Terminology and
topic drift can make future records rank worse. If the temporal number were
materially lower, the README claim would be overstated — this had to be checked
**before** pointing any review team at the repo (STATE action #6).

## Method (`backtest3_temporal.py`)

- Data: SYNERGY 1.0 `works_*.zip` (OpenAlex records) — every record carries
  `publication_date`/`publication_year`. Abstracts rebuilt from
  `abstract_inverted_index`. Labels from each review's `labels.csv`.
- Both splits run on **identical data per review**, identical protocol to the
  original backtest (TF-IDF 1–2grams, best of MultinomialNB vs balanced
  LogisticRegression by screen@95, same metrics):
  - **Random control:** stratified 80/20 (original protocol).
  - **Temporal:** train on the earliest ~80% by publication date, test on the
    latest ~20% (cutoff is a date boundary — a real update cursor is a date).
- The random control reproduced the original result (median WSS@95 = 84.8%),
  so differences are attributable to the split, not protocol drift.

## Results (26 reviews; 25 with ≥1 include in both test windows)

| Metric (median) | Random split | Temporal split |
|---|---|---|
| Screening needed for 95% recall | 10.2% | **24.1%** |
| WSS@95 | 84.8% | **70.9%** |
| Screening needed for 100% recall | 10.2% | 26.9% |

- Median per-review WSS@95 delta (temporal − random): **−2.5 pts** (mean −5.4).
- **12/25 reviews are >5 pts worse temporally.** Some collapse badly
  (Moran_2021: 0.8% WSS; Chou_2003: 30.8% vs 92.6% random); others are
  unaffected or better (Appenzeller-Herzog_2019 jumps from 1.4% to 79.9% —
  variance cuts both ways).
- One review (Chou_2004) had **zero includes** in its temporal test window — a
  realistic update outcome the random split can never produce.

Full per-review table: `backtest3-output.txt`.

## Interpretation

1. **The core mechanic still works under the honest split.** Median: screen the
   top ~24% of new records to catch 95% of the relevant ones — a ~71% work
   saving. That is a real, useful effect on a true original→update simulation.
2. **The old headline was overstated.** ~84% → ~71% median, and per-review
   variance is much wider temporally. The README must lead with the temporal
   number and say the per-review spread out loud (worst observed: ~1% saved).
3. **The digest's per-review calibration is the right safety mechanism** — a
   global median is not a promise for *your* review. This backtest strengthens
   the case for the tool's existing design (per-team CV calibration +
   low-confidence warning + never-auto-exclude).

## Action taken

README evidence section rewritten to lead with the temporal numbers; the
random-split figure retained as a secondary, clearly-labelled comparison.
Both backtest scripts + results shipped in `eval/`.
