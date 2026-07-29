"""Orchestrate one update run for a review.

Order matters for correctness:
  1. Load prior decisions (train/calibration data) and seed the deduper from
     the corpus store PLUS the prior decisions — both are records a human has
     already seen.
  2. Per source: fetch since the source's last successful run, ledger the
     fetched records in the store, and only then advance the source's cursor —
     to the date this run STARTED, so nothing published mid-run slips the
     window (runs overlap by a day by design; dedupe absorbs the boundary).
  3. Dedupe all fetched records (across sources and against the seeded corpus).
  4. Train on prior decisions, rank the new candidates, calibrate the
     recall/effort table, write digest + RIS.

A source that fails mid-run raises after the store has ledgered any earlier
sources' records but WITHOUT advancing the failed source's cursor, so the next
run re-fetches its window; the store's exact-match idempotency makes that safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from .classifier import RelevanceRanker, calibrate_screening_effort
from .config import ReviewConfig
from .decisions import load_decisions
from .dedupe import Deduper, Record
from .digest import DigestInput, RankedCandidate, render_markdown
from .ris import write_ris
from .sources import europepmc, pubmed

KNOWN_SOURCES = ("pubmed", "europepmc")


@dataclass
class RunResult:
    digest_path: str
    reimport_path: str | None
    source_counts: dict[str, int]
    n_new_candidates: int


def _fetch_source(name: str, source_cfg: dict, cfg: ReviewConfig,
                  since: str | None, client: httpx.Client | None) -> list[Record]:
    query = (source_cfg or {}).get("query")
    if not query:
        raise ValueError(f"sources.{name}.query is required.")
    if name == "pubmed":
        pm_since = since.replace("-", "/") if since else None
        return pubmed.fetch(query, email=cfg.contact_email, since=pm_since, client=client)
    if name == "europepmc":
        return europepmc.fetch(query, since=since, client=client)
    raise ValueError(f"Unknown source {name!r}; supported: {KNOWN_SOURCES}")


def _digest_path(digest_dir: Path, run_date: str) -> Path:
    path = digest_dir / f"{run_date}-update.md"
    n = 2
    while path.exists():
        path = digest_dir / f"{run_date}-update-{n}.md"
        n += 1
    return path


def run_update(cfg: ReviewConfig,
               clients: dict[str, httpx.Client] | None = None,
               today: str | None = None) -> RunResult:
    """Run one full update pass. `clients` maps source name -> injectable
    httpx.Client (for tests); `today` overrides the run date (ISO)."""
    from .store import CorpusStore

    clients = clients or {}
    run_date = today or date.today().isoformat()
    decisions = load_decisions(cfg.prior_decisions)

    with CorpusStore(cfg.corpus_db) as store:
        deduper = Deduper()
        deduper.load_corpus(store.all_records())
        deduper.load_corpus([
            Record(title=t, abstract=a)
            for t, a in zip(decisions.titles, decisions.abstracts)
        ])

        source_counts: dict[str, int] = {}
        fetched: list[Record] = []
        for name, source_cfg in cfg.sources.items():
            since = store.get_last_run(name)
            records = _fetch_source(name, source_cfg, cfg, since, clients.get(name))
            source_counts[name] = len(records)
            fetched.extend(records)
            store.add_records(records, seen_at=run_date)
            store.set_last_run(name, run_date)

        new_candidates = deduper.filter_new(fetched)

    ranked: list[RankedCandidate] = []
    calibration: dict[float, float | None] = {}
    reimport_path: str | None = None
    if new_candidates:
        ranker = RelevanceRanker().fit(
            decisions.titles, decisions.abstracts, decisions.labels
        )
        order = ranker.rank(
            [r.title for r in new_candidates],
            [r.abstract for r in new_candidates],
        )
        ranked = [RankedCandidate(record=new_candidates[rr.index], score=rr.score)
                  for rr in order]
        calibration = calibrate_screening_effort(
            decisions.titles, decisions.abstracts, decisions.labels,
            targets=cfg.report_recall_targets,
        )
        write_ris([c.record for c in ranked], cfg.reimport_ris)
        reimport_path = cfg.reimport_ris

    digest_dir = Path(cfg.digest_dir)
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest = DigestInput(
        review_name=cfg.name,
        run_date=run_date,
        source_counts=source_counts,
        n_after_dedupe=len(new_candidates),
        n_prior_decisions=len(decisions),
        n_prior_included=decisions.n_included,
        calibration=calibration,
        ranked=ranked,
        reimport_path=reimport_path,
    )
    digest_path = _digest_path(digest_dir, run_date)
    digest_path.write_text(render_markdown(digest), encoding="utf-8")

    return RunResult(
        digest_path=str(digest_path),
        reimport_path=reimport_path,
        source_counts=source_counts,
        n_new_candidates=len(new_candidates),
    )
