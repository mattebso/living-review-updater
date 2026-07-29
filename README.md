# Living Review Updater

**Keep your systematic review up to date — without re-screening thousands of records by hand, and without leaving the screening tool you already use.**

Maintaining a *living* systematic review means periodically re-running your searches and screening every new result. That screening burden is the #1 reason living reviews get abandoned ([Cochrane, 2025](https://www.cochranelibrary.com/) found only about half of a cohort of living reviews were ever updated). Existing automation either locks you inside a commercial platform (Nested Knowledge, DistillerSR) or makes you do the search-and-re-import by hand (ASReview). This tool fills the gap: it re-runs your searches, removes what you've already seen, and uses **your own prior include/exclude decisions** to put the most likely-relevant new studies at the top of the pile — then hands them back to the screening tool you already use.

> **Status: early development (v0, pre-release).** The full pipeline now runs end to end — searches, dedupe, ranking, digest and ASReview re-import — and has been exercised against the live PubMed and Europe PMC APIs. The core relevance mechanic is validated (see below). Still missing before production use: a true original→update backtest with a real review team, and packaging/release to PyPI.

## Does the core idea actually work?

Yes — measured on 26 real systematic reviews (the public [SYNERGY](https://github.com/asreview/synergy-dataset) dataset). Training a classifier on a review's prior screening decisions and ranking a held-out "new batch":

| | Median across 26 reviews |
|---|---|
| Screening needed to catch **95%** of new relevant studies | **~11%** of the new records |
| Screening work saved at 95% recall (WSS@95) | **~84%** |

In plain terms: instead of reading every new search result, a team could read roughly the top tenth and still catch ~95% of what matters. This matches the published research on these datasets. Full method and honest caveats: [`eval/backtest-RESULTS.md`](eval/backtest-RESULTS.md).

## Design principles (safety first)

Getting this wrong could hide a relevant study and bias a medical or policy conclusion. So:

1. **Rank and flag — never auto-exclude.** The tool orders records by likely relevance; a human always makes the include/exclude call and stays accountable.
2. **Recall-first, and honest about it.** Every run reports how much you'd need to screen to hit 95% / 99% / 100% recall on that batch, so *you* decide where to stop. It never claims to have found everything.
3. **Human-in-the-loop is mandatory**, per the Cochrane Handbook (Ch. 22) and the RAISE / PRISMA-trAIce guidance on AI in evidence synthesis.
4. **Keep your existing tool.** Output re-imports into ASReview (v1); the tool does not replace your screening workflow.
5. **Open and self-hostable.** Your search corpus and decisions never leave your machine. Free public APIs only; no always-on server needed.

## How it works

1. Describe your review once in a small config file — your saved search per database, plus a CSV export of your prior screening decisions. Start from [`examples/review.example.yaml`](examples/review.example.yaml).
2. Run it:

   ```bash
   living-review run --config review.yaml
   ```

   Each run re-runs the searches (PubMed + Europe PMC), fetching only what is new since that source's last successful run → removes records already in your corpus or already screened → ranks the rest with a classifier trained on your prior decisions → writes a Markdown digest and a ranked RIS file.
3. Read the digest, then re-import `new_candidates.ris` into ASReview and screen top-down.
4. Run it on a cron or a scheduled GitHub Action.

### What a run produces

- **`digests/<date>-update.md`** — how many records each source returned, how many survived dedupe, the calibration table (how far down the ranking you must screen for 95% / 99% / 100% recall, estimated by cross-validation on *your own* prior decisions), and the full ranked list. If you have few included records the digest says so plainly and tells you not to use the table as a stopping rule.
- **`new_candidates.ris`** — the same candidates in ranked order, for re-import into ASReview or any reference manager.
- **`corpus.sqlite`** — the local ledger of everything seen, plus each source's incremental cursor. Nothing leaves your machine.

### Prior decisions format

A CSV with `title`, `abstract`, and a label column (`included`, `label_included`, or `included_final`), where `1` = included and `0` = excluded. Rows labelled `-1` or left blank are treated as never screened and ignored. This is what ASReview exports.

## License

MIT — see [LICENSE](LICENSE). Built in the open as a public good; contributions welcome.
