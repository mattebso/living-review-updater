"""Tests for the prior-decisions loader, digest renderer, and RIS writer."""
import pytest

from livingreview.decisions import load_decisions
from livingreview.dedupe import Record
from livingreview.digest import DigestInput, RankedCandidate, render_markdown
from livingreview.ris import write_ris

# ------------------------------------------------------------- decisions

CSV_OK = (
    "title,abstract,included\n"
    "Included one,About magnesium,1\n"
    "Included two,More magnesium,1\n"
    "Included three,Even more magnesium,1\n"
    "Excluded one,About hips,0\n"
    "Excluded two,About coffee,0\n"
    "Excluded three,About soil,0\n"
    "Unscreened,Never looked at,-1\n"
    "Unscreened blank,Also never looked at,\n"
)


def test_load_decisions_parses_and_skips_unscreened(tmp_path):
    p = tmp_path / "decisions.csv"
    p.write_text(CSV_OK)
    d = load_decisions(p)
    assert len(d) == 6
    assert d.n_included == 3
    assert d.n_excluded == 3
    assert d.n_unlabeled_skipped == 2


def test_load_decisions_accepts_asreview_label_column(tmp_path):
    p = tmp_path / "decisions.csv"
    p.write_text(CSV_OK.replace("included\n", "label_included\n", 1))
    assert load_decisions(p).n_included == 3


def test_load_decisions_rejects_too_few(tmp_path):
    p = tmp_path / "decisions.csv"
    p.write_text("title,abstract,included\nA,x,1\nB,y,0\nC,z,0\nD,w,0\n")
    with pytest.raises(ValueError, match="at least 3 included"):
        load_decisions(p)


def test_load_decisions_rejects_missing_label_column(tmp_path):
    p = tmp_path / "decisions.csv"
    p.write_text("title,abstract\nA,x\n")
    with pytest.raises(ValueError, match="no label column"):
        load_decisions(p)


# ----------------------------------------------------------------- digest

def _digest_input(**overrides):
    base = dict(
        review_name="Test review",
        run_date="2026-07-29",
        source_counts={"pubmed": 5, "europepmc": 3},
        n_after_dedupe=2,
        n_prior_decisions=100,
        n_prior_included=20,
        calibration={0.95: 0.30, 1.0: None},
        ranked=[
            RankedCandidate(Record(title="Top hit", doi="10.1/top",
                                   source_id="pmid:1"), 0.91),
            RankedCandidate(Record(title="Second hit"), 0.42),
        ],
        reimport_path="new_candidates.ris",
    )
    base.update(overrides)
    return DigestInput(**base)


def test_digest_contains_safety_notice_counts_and_ranking():
    md = render_markdown(_digest_input())
    assert "never excludes anything" in md
    assert "pubmed: 5 record(s)" in md
    assert "**2 new candidate(s)**" in md and "6 duplicate" in md
    assert "| 95% | 30% |" in md
    assert "| 100% | n/a (too few decisions) |" in md
    assert "1. [0.910] Top hit (10.1/top · pmid:1)" in md
    assert "2. [0.420] Second hit" in md
    assert "new_candidates.ris" in md


def test_digest_zero_new_candidates_is_calm():
    md = render_markdown(_digest_input(
        n_after_dedupe=0, ranked=[], calibration={}, reimport_path=None))
    assert "No new candidates this run" in md
    assert "Ranked new candidates" not in md
    assert "never excludes anything" in md  # safety notice always present


# -------------------------------------------------------------------- RIS

def test_write_ris_round_trippable_and_ordered(tmp_path):
    p = tmp_path / "out" / "candidates.ris"
    write_ris([
        Record(title="First\nrecord", abstract="Line1\nLine2", doi="10.1/a",
               source_id="pmid:9"),
        Record(title="Second record"),
    ], p)
    text = p.read_text()
    assert text.index("First record") < text.index("Second record")
    assert "TI  - First record" in text          # newline flattened
    assert "AB  - Line1 Line2" in text
    assert "DO  - 10.1/a" in text
    assert "ID  - pmid:9" in text
    assert text.count("TY  - JOUR") == 2
    assert text.count("ER  - ") == 2


def test_digest_warns_when_calibration_basis_is_thin():
    md = render_markdown(_digest_input(n_prior_decisions=11, n_prior_included=5))
    assert "Low-confidence calibration" in md
    assert "only 5 included records" in md


def test_digest_omits_warning_with_ample_decisions():
    md = render_markdown(_digest_input(n_prior_decisions=400, n_prior_included=60))
    assert "Low-confidence calibration" not in md
