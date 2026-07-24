"""Deduplicate newly-fetched records against the review's existing corpus and
against each other. DOI match first (exact, normalized), then fuzzy title match
as a fallback for records missing a DOI or with preprint/published duplicates.

Deduplication is deliberately conservative on the *corpus* side (don't re-show
what a human already screened) but must NOT drop a genuinely new study — when in
doubt, keep it and let the human decide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def normalize_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (title or "").lower()).strip()


@dataclass
class Record:
    title: str
    abstract: str = ""
    doi: str | None = None
    source_id: str | None = None


@dataclass
class Deduper:
    title_threshold: int = 92  # rapidfuzz token_sort_ratio; tuned conservatively
    _seen_dois: set[str] = field(default_factory=set)
    _seen_titles: list[str] = field(default_factory=list)

    def load_corpus(self, records: list[Record]) -> None:
        for r in records:
            nd = normalize_doi(r.doi)
            if nd:
                self._seen_dois.add(nd)
            nt = normalize_title(r.title)
            if nt:
                self._seen_titles.append(nt)

    def is_new(self, r: Record) -> bool:
        nd = normalize_doi(r.doi)
        if nd and nd in self._seen_dois:
            return False
        nt = normalize_title(r.title)
        if not nt:
            return True  # no title to compare -> keep, let human decide
        for seen in self._seen_titles:
            if fuzz.token_sort_ratio(nt, seen) >= self.title_threshold:
                return False
        return True

    def filter_new(self, records: list[Record]) -> list[Record]:
        out: list[Record] = []
        for r in records:
            if self.is_new(r):
                out.append(r)
                # add to seen so intra-batch duplicates are also removed
                nd = normalize_doi(r.doi)
                if nd:
                    self._seen_dois.add(nd)
                nt = normalize_title(r.title)
                if nt:
                    self._seen_titles.append(nt)
        return out
