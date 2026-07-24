"""Connector tests against mocked HTTP transports — no live API calls."""
import json

import httpx
import pytest

from livingreview.sources import europepmc, pubmed

# ---------------------------------------------------------------- PubMed

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">11111</PMID>
      <Article>
        <ArticleTitle>Magnesium for <i>acute</i> asthma</ArticleTitle>
        <ELocationID EIdType="doi" ValidYN="Y">10.1000/mg.asthma</ELocationID>
        <Abstract>
          <AbstractText Label="BACKGROUND">Asthma is common.</AbstractText>
          <AbstractText Label="RESULTS">Magnesium helped.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">22222</PMID>
      <Article>
        <ArticleTitle>No-DOI trial</ArticleTitle>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/fallback.doi</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _pubmed_transport(seen_requests):
    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if "esearch" in str(request.url):
            body = {"esearchresult": {"count": "2", "idlist": ["11111", "22222"]}}
            return httpx.Response(200, json=body)
        return httpx.Response(200, content=PUBMED_XML)
    return httpx.MockTransport(handler)


def test_pubmed_fetch_parses_title_abstract_doi():
    seen = []
    client = httpx.Client(transport=_pubmed_transport(seen))
    recs = pubmed.fetch("magnesium asthma", email="t@example.org",
                        since="2026/01/01", client=client)
    assert len(recs) == 2
    r0 = recs[0]
    assert r0.title == "Magnesium for acute asthma"  # inline <i> flattened
    assert "BACKGROUND: Asthma is common." in r0.abstract
    assert r0.doi == "10.1000/mg.asthma"
    assert r0.source_id == "pmid:11111"
    # DOI fallback from PubmedData/ArticleIdList when ELocationID missing
    assert recs[1].doi == "10.1000/fallback.doi"


def test_pubmed_sends_etiquette_params_and_date_filter():
    seen = []
    client = httpx.Client(transport=_pubmed_transport(seen))
    pubmed.fetch("q", email="t@example.org", since="2026/01/01", client=client)
    es = next(r for r in seen if "esearch" in str(r.url))
    params = dict(httpx.QueryParams(es.url.query))
    assert params["email"] == "t@example.org"
    assert params["tool"] == "living-review-updater"
    assert params["datetype"] == "edat"
    assert params["mindate"] == "2026/01/01"


def test_pubmed_requires_email():
    with pytest.raises(ValueError):
        pubmed.fetch("q", email="")


def test_pubmed_refuses_oversized_result_sets():
    def handler(request):
        return httpx.Response(200, json={
            "esearchresult": {"count": "999999", "idlist": []}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(pubmed.PubMedError, match="Narrow the query"):
        pubmed.fetch("everything", email="t@example.org", client=client)


# ------------------------------------------------------------ Europe PMC

def _epmc_pages():
    page1 = {
        "hitCount": 3,
        "nextCursorMark": "CURSOR2",
        "resultList": {"result": [
            {"id": "100", "source": "MED", "title": "Trial one",
             "abstractText": "Abstract one.", "doi": "10.2000/one"},
            {"id": "200", "source": "PPR", "title": "Preprint two"},
        ]},
    }
    page2 = {
        "hitCount": 3,
        "nextCursorMark": "CURSOR2",  # unchanged cursor -> stop
        "resultList": {"result": [
            {"id": "300", "source": "MED", "title": "Trial three",
             "abstractText": "", "doi": "10.2000/three"},
        ]},
    }
    return {"*": page1, "CURSOR2": page2}


def test_europepmc_fetch_paginates_and_maps():
    pages = _epmc_pages()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        cursor = dict(httpx.QueryParams(request.url.query))["cursorMark"]
        return httpx.Response(200, json=pages[cursor])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    recs = europepmc.fetch("magnesium asthma", since="2026-01-01", client=client)
    assert [r.source_id for r in recs] == ["epmc:MED:100", "epmc:PPR:200", "epmc:MED:300"]
    assert recs[0].doi == "10.2000/one"
    assert recs[1].doi is None
    # date filter applied via CREATION_DATE clause
    q = dict(httpx.QueryParams(seen[0].url.query))["query"]
    assert "CREATION_DATE:[2026-01-01" in q


def test_europepmc_refuses_oversized_result_sets():
    def handler(request):
        return httpx.Response(200, json={"hitCount": 999999,
                                         "resultList": {"result": []}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(europepmc.EuropePMCError, match="Narrow the query"):
        europepmc.fetch("everything", client=client)
