"""PubMed source via NCBI E-utilities (free, no key required for low volume).

API etiquette (must respect or NCBI will IP-block):
  - Send tool= and email= on every request.
  - <= 3 requests/sec without an API key; up to 10/sec with a free key.
  - Run large jobs off-peak (US nighttime / weekends).
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/

Flow: esearch (get PMIDs for the saved query, optionally date-limited to since
the last run) -> efetch (titles + abstracts + DOIs). Returns dedupe.Record list.

STATUS: stub — implement esearch/efetch with httpx + XML parsing next.
"""
from __future__ import annotations

from ..dedupe import Record

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch(query: str, email: str, since: str | None = None,
          tool: str = "living-review-updater") -> list[Record]:
    """Return records matching `query` (optionally published since `since`,
    YYYY/MM/DD). Not yet implemented."""
    raise NotImplementedError(
        "PubMed connector not implemented yet. Next: esearch -> efetch with "
        "tool/email params and rate limiting; parse PubmedArticle XML for "
        "ArticleTitle, AbstractText, and ELocationID[@EIdType='doi']."
    )
