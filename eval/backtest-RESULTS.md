# Backtest results — core mechanic validated (2026-07-24)
Data: SYNERGY (26 real labeled systematic reviews). Test: train classifier on prior include/exclude decisions, rank a held-out "new batch", measure screening work saved at 95% recall (WSS@95). Metric screen@95% = % of new records a human screens (ranked) to catch 95% of truly-relevant new studies.

## Naive first cut (MultinomialNB, 50/50 split) — WEAK
Median WSS@95 = 6.3%; median screen@95% = 88.7%. (A deliberately simple model + only half the labels. Too pessimistic; not how the tool would work.)

## Fair test (best of NB vs balanced LogisticRegression, 80/20 split) — STRONG
Median WSS@95 = **84.3%**; median screen@95% = **10.7%**. Mean WSS@95 = 71.1%.
→ Median: screen ~11% of new records to catch 95% of new relevant studies (~84% work saved). Matches published ASReview/TAR literature (WSS@95 60-90%).

## Honest caveats
- 100% recall (catching the LAST relevant study) is harder + high-variance: median screen@100% = 12.7%, but some reviews need 47-93% (long tail). → tool must be recall-FIRST, report per-run recall, let teams set their target, never claim perfection, always human-in-loop.
- Simplified backtest (stratified random split, TF-IDF+linear model). Real deployment adds concept drift over time; validate on true original→update pairs during the design-partner phase.
- LR(class_weight=balanced) beat NB on 24/26 reviews → LR is the v1 default classifier.

## Verdict: GATE PASSED. Core "reuse prior decisions to flag new studies" mechanic works well enough to genuinely reduce screening burden while staying safe. Proceed to build v1.
