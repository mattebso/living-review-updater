"""Load a review team's prior screening decisions from a CSV export.

Expected columns (case-insensitive): `title`, `abstract`, and a label column —
`included`, `label_included`, or `included_final` (ASReview exports vary by
version). Label values 1/0 mean included/excluded; empty or -1 means the record
was never screened and is skipped (screening a record is a human act; we only
learn from decisions that were actually made).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

_LABEL_COLUMNS = ("included", "label_included", "included_final")


@dataclass
class PriorDecisions:
    titles: list[str]
    abstracts: list[str]
    labels: list[int]  # 1 = included, 0 = excluded
    n_unlabeled_skipped: int = 0

    def __len__(self) -> int:
        return len(self.titles)

    @property
    def n_included(self) -> int:
        return sum(self.labels)

    @property
    def n_excluded(self) -> int:
        return len(self.labels) - self.n_included


def load_decisions(path: str | Path) -> PriorDecisions:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Prior decisions file not found: {path}. Export your screening "
            "decisions from ASReview (or any CSV with title/abstract/included)."
        )
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty.")
        cols = {c.lower().strip(): c for c in reader.fieldnames}
        label_col = next((cols[c] for c in _LABEL_COLUMNS if c in cols), None)
        if label_col is None:
            raise ValueError(
                f"{path} has no label column. Expected one of {_LABEL_COLUMNS}; "
                f"found: {reader.fieldnames}"
            )
        if "title" not in cols:
            raise ValueError(f"{path} has no 'title' column; found: {reader.fieldnames}")
        title_col = cols["title"]
        abstract_col = cols.get("abstract")

        titles: list[str] = []
        abstracts: list[str] = []
        labels: list[int] = []
        skipped = 0
        for row in reader:
            raw = (row.get(label_col) or "").strip()
            if raw in ("", "-1"):
                skipped += 1
                continue
            if raw not in ("0", "1"):
                raise ValueError(
                    f"Unexpected label value {raw!r} in {path} (want 1/0, "
                    "or empty/-1 for unscreened)."
                )
            titles.append((row.get(title_col) or "").strip())
            abstracts.append((row.get(abstract_col) or "").strip() if abstract_col else "")
            labels.append(int(raw))

    decisions = PriorDecisions(titles, abstracts, labels, n_unlabeled_skipped=skipped)
    if decisions.n_included < 3 or decisions.n_excluded < 3:
        raise ValueError(
            f"Need at least 3 included and 3 excluded prior decisions to train "
            f"(got {decisions.n_included} included / {decisions.n_excluded} "
            f"excluded in {path})."
        )
    return decisions
