# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [0.1.0] — 2026-08-03

First packaged release. The full update pipeline works end to end and has been
verified against the live PubMed and Europe PMC APIs.

### Added
- **Relevance ranker** (`RelevanceRanker`): TF-IDF + balanced logistic regression
  trained on the review team's own prior screening decisions. Ranks new records
  for human screening; **never auto-excludes**.
- **Source connectors** for PubMed (esearch/efetch) and Europe PMC (cursorMark),
  with rate limiting, incremental since-date filters, and oversized-query guards.
- **Deduplication** against the existing corpus (normalized DOI exact match +
  fuzzy title matching).
- **SQLite corpus store**: idempotent record ledger plus per-source incremental
  cursors, safe to re-run after partial failures.
- **Prior-decisions loader** for ASReview-style CSV exports (unscreened rows skipped).
- **Digest renderer**: per-source counts, ranked candidate list, and a
  recall-calibration table computed by out-of-fold cross-validation on the
  team's own decisions — with an explicit low-confidence warning below 20
  included records (the table is not a stopping rule on thin data).
- **RIS writer** for re-importing ranked candidates into ASReview.
- **CLI**: `living-review run --config review.yaml`.
- **Evidence** (`eval/`): retrospective backtests on 26 SYNERGY reviews.
  Honest headline: **~71% median screening work saved at 95% recall** under a
  true original→update temporal split (wide per-review spread, 0.8%–94%);
  the earlier ~84.8% figure from a random split is retained as a labelled
  secondary result.

### Safety principles (unchanged from day one)
- The tool ranks and flags; a human makes every include/exclude decision.
- Calibration numbers come from the team's own data and are withheld or
  flagged when the data is too thin to support them.
