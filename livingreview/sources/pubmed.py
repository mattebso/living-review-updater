"""PubMed source via NCBI E-utilities (free, no key required for low volume).

API etiquette (must respect or NCBI will IP-block):
  - Send tool= and email= on every request.
  - <= 3 requests/sec without an API key; up to 10/sec with a free key.
  - Run large jobs off-peak (US nighttime / weekends).
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/

Flow: esearch (get PMIDs for the saved query, optionally date-limited to since
the last run) -> efetch in batches (titles + abstracts + DOIs). Returns
dedupe.Record list with source_id = "pmid:<PMID>".
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import httpx

from ..dedupe import Record

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Without an API key NCBI allows 3 req/s; stay under it with margin.
MIN_SECONDS_BETWEEN_REQUESTS = 0.4
ESEARCH_PAGE = 10_000  # esearch retmax cap per request
EFETCH_BATCH = 200     # PMIDs per efetch request

# Refuse to silently fetch unbounded result sets: a query matching this many
# records is almost certainly wrong (or needs the `since` date filter).
MAX_RESULTS = 50_000


class PubMedError(RuntimeError):
    pass


class _Throttle:
    def __init__(self, min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


def _get(client: httpx.Client, url: str, params: dict, throttle: _Throttle) -> httpx.Response:
    throttle.wait()
    resp = client.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp


def _esearch_pmids(client: httpx.Client, query: str, email: str, tool: str,
                   since: str | None, throttle: _Throttle) -> list[str]:
    pmids: list[str] = []
    retstart = 0
    while True:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": ESEARCH_PAGE,
            "retstart": retstart,
            "tool": tool,
            "email": email,
        }
        if since:
            # EDAT = Entrez date (when the record entered PubMed) — the right
            # axis for "what appeared since our last run", robust to journals
            # backfilling old publication dates.
            params.update({"datetype": "edat", "mindate": since, "maxdate": "3000"})
        data = _get(client, ESEARCH, params, throttle).json()
        result = data.get("esearchresult", {})
        if "ERROR" in result or "error" in data:
            raise PubMedError(f"esearch error: {result.get('ERROR') or data.get('error')}")
        count = int(result.get("count", 0))
        if count > MAX_RESULTS:
            raise PubMedError(
                f"Query matches {count} records (> {MAX_RESULTS}). Narrow the "
                "query or set a since-date; refusing an unbounded bulk fetch."
            )
        pmids.extend(result.get("idlist", []))
        retstart += ESEARCH_PAGE
        if retstart >= count or not result.get("idlist"):
            break
    return pmids


def _text(el: ET.Element | None) -> str:
    """Flatten an element's text including inline markup (<i>, <sup>, ...)."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _parse_articles(xml_bytes: bytes) -> list[Record]:
    root = ET.fromstring(xml_bytes)
    out: list[Record] = []
    for art in root.iter("PubmedArticle"):
        pmid = _text(art.find(".//MedlineCitation/PMID"))
        title = _text(art.find(".//Article/ArticleTitle"))
        # Abstracts may be split into labeled sections (BACKGROUND/METHODS/...).
        parts = []
        for ab in art.findall(".//Article/Abstract/AbstractText"):
            label = ab.get("Label")
            txt = _text(ab)
            parts.append(f"{label}: {txt}" if label else txt)
        abstract = "\n".join(p for p in parts if p)
        doi = None
        for eloc in art.findall(".//Article/ELocationID"):
            if eloc.get("EIdType") == "doi":
                doi = _text(eloc) or None
                break
        if doi is None:
            for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = _text(aid) or None
                    break
        out.append(Record(title=title, abstract=abstract, doi=doi,
                          source_id=f"pmid:{pmid}" if pmid else None))
    return out


def fetch(query: str, email: str, since: str | None = None,
          tool: str = "living-review-updater",
          client: httpx.Client | None = None) -> list[Record]:
    """Return records matching `query`, optionally limited to records that
    entered PubMed since `since` (YYYY/MM/DD).

    `client` is injectable for tests (httpx.MockTransport).
    """
    if not email:
        raise ValueError("email is required (NCBI API etiquette).")
    throttle = _Throttle()
    own_client = client is None
    client = client or httpx.Client()
    try:
        pmids = _esearch_pmids(client, query, email, tool, since, throttle)
        records: list[Record] = []
        for i in range(0, len(pmids), EFETCH_BATCH):
            batch = pmids[i:i + EFETCH_BATCH]
            resp = _get(client, EFETCH, {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
                "tool": tool,
                "email": email,
            }, throttle)
            records.extend(_parse_articles(resp.content))
        return records
    finally:
        if own_client:
            client.close()
