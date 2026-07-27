"""SQLite corpus store: everything the review has already seen, plus per-source
incremental state (the date each connector last fetched successfully).

Two jobs:
  1. Dedupe ledger. Every record ever surfaced to the team (the imported
     existing corpus + each run's new candidates) is stored so `Deduper` can be
     seeded from it and nothing is re-shown across runs.
  2. Incremental fetch state. `get_last_run(source)` feeds each connector's
     `since` filter; the caller advances it with `set_last_run` only after a
     successful fetch. Dates are inclusive and day-granular, so consecutive
     runs overlap by design: re-fetching a boundary record and dropping it in
     dedupe is fine, missing one is not.

Dates are ISO YYYY-MM-DD (Europe PMC's format; convert with
`date.replace("-", "/")` for PubMed's YYYY/MM/DD).

Idempotency is exact-match only (same source_id, or same normalized DOI when
there is no source_id): re-adding an already-stored record is a no-op. Cross-
source duplicates (the same paper via PubMed and Europe PMC) are the fuzzy
`Deduper`'s job, not the store's.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .dedupe import Record, normalize_doi

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    doi TEXT,                    -- normalized: lowercase, no doi.org prefix
    source_id TEXT,              -- e.g. pmid:123 / epmc:MED:456
    first_seen TEXT NOT NULL     -- ISO date the pipeline first recorded it
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_records_source_id
    ON records(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_records_doi ON records(doi);
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,     -- connector name, e.g. "pubmed" / "europepmc"
    last_run TEXT NOT NULL       -- ISO date of the last successful fetch
);
"""


class CorpusStore:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "CorpusStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------- records

    def add_records(self, records: list[Record], seen_at: str | None = None) -> int:
        """Store records; returns how many were actually new to the store.

        Exact duplicates (same source_id, or same normalized DOI for records
        without a source_id) are skipped silently, so re-running a fetch after
        a partial failure is safe.
        """
        seen_at = seen_at or date.today().isoformat()
        inserted = 0
        cur = self._conn.cursor()
        for r in records:
            nd = normalize_doi(r.doi)
            if r.source_id is None and nd is not None:
                already = cur.execute(
                    "SELECT 1 FROM records WHERE source_id IS NULL AND doi = ?",
                    (nd,),
                ).fetchone()
                if already:
                    continue
            cur.execute(
                "INSERT OR IGNORE INTO records (title, abstract, doi, source_id, first_seen)"
                " VALUES (?, ?, ?, ?, ?)",
                (r.title, r.abstract or "", nd, r.source_id, seen_at),
            )
            inserted += cur.rowcount
        self._conn.commit()
        return inserted

    def all_records(self) -> list[Record]:
        """Everything ever seen — feed this to Deduper.load_corpus()."""
        rows = self._conn.execute(
            "SELECT title, abstract, doi, source_id FROM records ORDER BY id"
        ).fetchall()
        return [Record(title=t, abstract=a, doi=d, source_id=s)
                for t, a, d, s in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    # -------------------------------------------------------- source state

    def get_last_run(self, source: str) -> str | None:
        """ISO date of the last successful fetch for `source`, or None if the
        source has never run (caller must then fetch without a since-filter or
        seed the corpus another way)."""
        row = self._conn.execute(
            "SELECT last_run FROM source_state WHERE source = ?", (source,)
        ).fetchone()
        return row[0] if row else None

    def set_last_run(self, source: str, run_date: str) -> None:
        """Advance the incremental cursor. Call only after the fetch AND the
        corresponding add_records() both succeeded, with the date the run
        STARTED (not finished) so nothing published mid-run slips the window."""
        self._conn.execute(
            "INSERT INTO source_state (source, last_run) VALUES (?, ?)"
            " ON CONFLICT(source) DO UPDATE SET last_run = excluded.last_run",
            (source, run_date),
        )
        self._conn.commit()
