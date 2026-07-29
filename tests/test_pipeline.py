"""End-to-end pipeline test against mocked HTTP transports — no live calls.

Covers the full wiring: config -> prior decisions -> fetch (both sources) ->
store ledger + incremental cursors -> dedupe -> rank -> digest + RIS. Then a
second run to prove idempotency (everything dedupes away, cursor advanced).
"""
import httpx
import yaml

from livingreview.config import ReviewConfig
from livingreview.pipeline import run_update
from livingreview.store import CorpusStore

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">11111</PMID>
      <Article>
        <ArticleTitle>Intravenous magnesium in acute severe asthma trial</ArticleTitle>
        <ELocationID EIdType="doi" ValidYN="Y">10.1000/mg.new</ELocationID>
        <Abstract><AbstractText>IV magnesium improved asthma outcomes.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _pubmed_client():
    def handler(request: httpx.Request) -> httpx.Response:
        if "esearch" in str(request.url):
            return httpx.Response(200, json={
                "esearchresult": {"count": "1", "idlist": ["11111"]}})
        return httpx.Response(200, content=PUBMED_XML)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _epmc_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "hitCount": 2,
            "nextCursorMark": "*",  # unchanged cursor -> single page
            "resultList": {"result": [
                # same paper as the PubMed record (cross-source dup, same DOI)
                {"id": "500", "source": "MED", "doi": "10.1000/mg.new",
                 "title": "Intravenous magnesium in acute severe asthma trial",
                 "abstractText": "IV magnesium improved asthma outcomes."},
                # genuinely distinct second record, off-topic
                {"id": "600", "source": "MED", "doi": "10.1000/soil.new",
                 "title": "Soil carbon dynamics under crop rotation",
                 "abstractText": "We measured soil carbon over ten years."},
            ]},
        })
    return httpx.Client(transport=httpx.MockTransport(handler))


DECISIONS_CSV = (
    "title,abstract,included\n"
    "Magnesium sulfate for acute asthma,IV magnesium trial in asthma.,1\n"
    "Nebulized magnesium in the ED,Magnesium reduced asthma admissions.,1\n"
    "Magnesium for bronchospasm,Magnesium improved lung function in asthma.,1\n"
    "IV magnesium in pediatric asthma,Magnesium trial in children with asthma.,1\n"
    "Hip replacement outcomes,Arthroplasty recovery times.,0\n"
    "Coffee and cardiovascular risk,Cohort study of coffee.,0\n"
    "Forest soil microbiomes,Soil bacterial communities sequenced.,0\n"
    "Machine translation quality,Neural MT across languages.,0\n"
)


def _write_config(tmp_path):
    (tmp_path / "decisions.csv").write_text(DECISIONS_CSV)
    cfg_path = tmp_path / "review.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "review": {"name": "e2e test review",
                   "contact_email": "t@example.org"},
        "sources": {"pubmed": {"query": "magnesium asthma"},
                    "europepmc": {"query": "magnesium asthma"}},
        "prior_decisions": str(tmp_path / "decisions.csv"),
        "corpus_db": str(tmp_path / "corpus.sqlite"),
        "output": {"digest": str(tmp_path / "digests"),
                   "reimport_ris": str(tmp_path / "new_candidates.ris")},
    }))
    return ReviewConfig.load(cfg_path)


def test_full_run_then_idempotent_second_run(tmp_path):
    cfg = _write_config(tmp_path)
    clients = {"pubmed": _pubmed_client(), "europepmc": _epmc_client()}

    result = run_update(cfg, clients=clients, today="2026-07-29")

    # 3 fetched (1 PubMed + 2 EPMC); the cross-source duplicate collapses -> 2 new
    assert result.source_counts == {"pubmed": 1, "europepmc": 2}
    assert result.n_new_candidates == 2

    # On-topic asthma record must outrank the soil record
    ris = (tmp_path / "new_candidates.ris").read_text()
    assert ris.index("magnesium in acute severe asthma") < ris.index("Soil carbon")

    digest = (tmp_path / "digests" / "2026-07-29-update.md").read_text()
    assert "never excludes anything" in digest
    assert "**2 new candidate(s)**" in digest
    assert "Screening effort vs. recall" in digest

    # Ledger has all 3 fetched records; both cursors advanced to the run date
    with CorpusStore(cfg.corpus_db) as store:
        assert store.count() == 3
        assert store.get_last_run("pubmed") == "2026-07-29"
        assert store.get_last_run("europepmc") == "2026-07-29"

    # Second run: same upstream responses -> everything already seen, 0 new
    clients2 = {"pubmed": _pubmed_client(), "europepmc": _epmc_client()}
    result2 = run_update(cfg, clients=clients2, today="2026-07-30")
    assert result2.n_new_candidates == 0
    assert result2.reimport_path is None
    digest2 = (tmp_path / "digests" / "2026-07-30-update.md").read_text()
    assert "No new candidates this run" in digest2
    with CorpusStore(cfg.corpus_db) as store:
        assert store.count() == 3  # no ledger bloat
        assert store.get_last_run("pubmed") == "2026-07-30"
