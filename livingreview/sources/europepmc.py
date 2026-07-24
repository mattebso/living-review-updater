"""Europe PMC source (free REST API, ~10 req/s, no key required).
Docs: https://europepmc.org/RestfulWebService

Flow: GET /search with the saved query (optionally date-limited via CREATION_DATE,
i.e. when the record entered Europe PMC — the right axis for "new since last
run"), paginate via cursorMark, map results to dedupe.Record with
source_id = "epmc:<source>:<id>".
"""
from __future__ import annotations

import time

import httpx

from ..dedupe import Record

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

PAGE_SIZE = 1000
MIN_SECONDS_BETWEEN_REQUESTS = 0.15  # stay well under ~10 req/s
MAX_RESULTS = 50_000  # refuse unbounded bulk fetches (query likely wrong)


class EuropePMCError(RuntimeError):
    pass


def _date_filtered(query: str, since: str | None) -> str:
    if not since:
        return query
    # since: YYYY-MM-DD. CREATION_DATE = when the record entered Europe PMC.
    return f"({query}) AND (CREATION_DATE:[{since} TO 3000-12-31])"


def fetch(query: str, since: str | None = None,
          client: httpx.Client | None = None) -> list[Record]:
    """Return records matching `query`, optionally limited to records created
    in Europe PMC since `since` (YYYY-MM-DD).

    `client` is injectable for tests (httpx.MockTransport).
    """
    own_client = client is None
    client = client or httpx.Client()
    records: list[Record] = []
    cursor = "*"
    last_request = 0.0
    try:
        while True:
            delta = time.monotonic() - last_request
            if delta < MIN_SECONDS_BETWEEN_REQUESTS:
                time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - delta)
            last_request = time.monotonic()
            resp = client.get(SEARCH, params={
                "query": _date_filtered(query, since),
                "format": "json",
                "resultType": "core",
                "pageSize": PAGE_SIZE,
                "cursorMark": cursor,
            }, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            hit_count = int(data.get("hitCount", 0))
            if hit_count > MAX_RESULTS:
                raise EuropePMCError(
                    f"Query matches {hit_count} records (> {MAX_RESULTS}). "
                    "Narrow the query or set a since-date; refusing an "
                    "unbounded bulk fetch."
                )
            results = (data.get("resultList") or {}).get("result") or []
            for r in results:
                src = r.get("source", "")
                rid = r.get("id", "")
                records.append(Record(
                    title=(r.get("title") or "").strip(),
                    abstract=(r.get("abstractText") or "").strip(),
                    doi=r.get("doi") or None,
                    source_id=f"epmc:{src}:{rid}" if rid else None,
                ))
            next_cursor = data.get("nextCursorMark")
            if not results or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return records
    finally:
        if own_client:
            client.close()
