"""Build the per-run digest: the honest, human-facing summary of an update run.

The digest is where the safety contract lives in practice. For the new batch it
reports, using the review's own held-out prior decisions as a calibration check:
  - how many new records were found (after dedupe),
  - the ranked list for screening,
  - for each recall target (e.g. 95/99/100%), how far down the ranked list the
    team must screen to plausibly reach it,
  - an explicit reminder that the tool never auto-excludes.

STATUS: stub — render Markdown + write the ASReview re-import file next.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DigestInput:
    review_name: str
    n_found: int
    n_after_dedupe: int
    # ranked new records + calibration recall/effort estimates get added here.


def render_markdown(d: DigestInput) -> str:
    raise NotImplementedError(
        "Digest rendering not implemented yet. Must include: found/new counts, "
        "ranked candidates, screen-fraction-for-recall at each target, and the "
        "'ranks for human review; never auto-excludes' notice."
    )
