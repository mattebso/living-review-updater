"""Load and validate a per-review YAML config (see examples/review.example.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ReviewConfig:
    name: str
    contact_email: str
    sources: dict
    prior_decisions: str
    corpus_db: str = "corpus.sqlite"
    report_recall_targets: list[float] = field(default_factory=lambda: [0.95, 0.99, 1.0])
    digest_dir: str = "digests/"
    reimport_ris: str = "new_candidates.ris"

    @staticmethod
    def load(path: str | Path) -> "ReviewConfig":
        data = yaml.safe_load(Path(path).read_text())
        review = data.get("review", {})
        if not review.get("contact_email"):
            raise ValueError("review.contact_email is required (PubMed/NCBI API etiquette).")
        if not data.get("sources"):
            raise ValueError("At least one source (pubmed / europepmc) is required.")
        out = data.get("output", {})
        screening = data.get("screening", {})
        return ReviewConfig(
            name=review.get("name", "unnamed-review"),
            contact_email=review["contact_email"],
            sources=data["sources"],
            prior_decisions=data["prior_decisions"],
            corpus_db=data.get("corpus_db", "corpus.sqlite"),
            report_recall_targets=screening.get("report_recall_targets", [0.95, 0.99, 1.0]),
            digest_dir=out.get("digest", "digests/"),
            reimport_ris=out.get("reimport_ris", "new_candidates.ris"),
        )
