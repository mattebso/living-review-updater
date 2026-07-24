"""Data-source connectors. Each exposes fetch(...) -> list[dedupe.Record]."""
from . import europepmc, pubmed

__all__ = ["pubmed", "europepmc"]
