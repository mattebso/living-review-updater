"""Europe PMC source (free REST API, ~10 req/s, no key required).
Docs: https://europepmc.org/RestfulWebService

Flow: GET /search with the saved query + a date filter, paginate via cursorMark,
map results to dedupe.Record (title, abstractText, doi).

STATUS: stub — implement paginated search next.
"""
from __future__ import annotations

from ..dedupe import Record

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch(query: str, since: str | None = None) -> list[Record]:
    raise NotImplementedError(
        "Europe PMC connector not implemented yet. Next: paginated GET /search "
        "with format=json, resultType=core, cursorMark; map title/abstractText/doi."
    )
