"""CorpusStore tests: roundtrip, idempotency, incremental state, persistence,
and integration with the Deduper (store -> load_corpus -> filter_new)."""
from livingreview.dedupe import Deduper, Record
from livingreview.store import CorpusStore


def _recs():
    return [
        Record(title="Magnesium for acute asthma",
               abstract="RCT of IV magnesium.",
               doi="https://doi.org/10.1000/MG.asthma",
               source_id="pmid:11111"),
        Record(title="No-DOI trial", source_id="epmc:MED:22222"),
        Record(title="Legacy import, no source id", doi="10.1000/legacy"),
    ]


def test_roundtrip_and_doi_normalization(tmp_path):
    with CorpusStore(tmp_path / "c.sqlite") as store:
        assert store.add_records(_recs(), seen_at="2026-07-27") == 3
        out = store.all_records()
        assert [r.source_id for r in out] == ["pmid:11111", "epmc:MED:22222", None]
        assert out[0].doi == "10.1000/mg.asthma"  # normalized on write
        assert out[0].abstract == "RCT of IV magnesium."
        assert store.count() == 3


def test_re_add_is_idempotent(tmp_path):
    with CorpusStore(tmp_path / "c.sqlite") as store:
        store.add_records(_recs())
        # same source_id, and same DOI for the source_id-less record -> no-ops
        assert store.add_records(_recs()) == 0
        assert store.count() == 3


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "c.sqlite"
    with CorpusStore(path) as store:
        store.add_records(_recs())
        store.set_last_run("pubmed", "2026-07-27")
    with CorpusStore(path) as store:
        assert store.count() == 3
        assert store.get_last_run("pubmed") == "2026-07-27"


def test_last_run_state(tmp_path):
    with CorpusStore(tmp_path / "c.sqlite") as store:
        assert store.get_last_run("pubmed") is None  # never run -> full fetch
        store.set_last_run("pubmed", "2026-07-01")
        store.set_last_run("pubmed", "2026-07-27")  # advances
        assert store.get_last_run("pubmed") == "2026-07-27"
        assert store.get_last_run("europepmc") is None  # per-source, independent


def test_feeds_deduper(tmp_path):
    with CorpusStore(tmp_path / "c.sqlite") as store:
        store.add_records(_recs())
        deduper = Deduper()
        deduper.load_corpus(store.all_records())
        fetched = [
            # already seen: DOI matches (different formatting, no source_id)
            Record(title="Different title entirely", doi="10.1000/mg.ASTHMA"),
            # already seen: same title, punctuation/case differ, no DOI
            Record(title="No-DOI Trial."),
            # genuinely new
            Record(title="A brand new unrelated study", doi="10.9999/new"),
        ]
        new = deduper.filter_new(fetched)
        assert [r.doi for r in new] == ["10.9999/new"]
