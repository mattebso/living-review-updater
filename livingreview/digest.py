"""Build the per-run digest: the honest, human-facing summary of an update run.

The digest is where the safety contract lives in practice. For each new batch it
reports:
  - how many records each source returned and how many survived dedupe,
  - a calibration table (from cross-validation on the review's OWN prior
    decisions): for each recall target, how far down a ranked list the team
    must plausibly screen to reach it,
  - the ranked new candidates,
  - an explicit reminder that the tool never auto-excludes, and that the
    calibration numbers are estimates, not guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dedupe import Record

SAFETY_NOTICE = (
    "**This tool ranks for human review; it never excludes anything.** Every "
    "record listed below should be screened by a human. The calibration table "
    "estimates — from your own prior decisions, via cross-validation — how far "
    "down the ranking you must screen to reach a given recall. It is an "
    "estimate, not a guarantee: if missing a study is unacceptable, screen the "
    "full list."
)

# Below this many included prior decisions, the recall estimate is quantized so
# coarsely (one included record = 1/N of total recall) that reporting it without
# a warning would imply precision the data cannot support.
MIN_INCLUDED_FOR_CONFIDENT_CALIBRATION = 20


@dataclass
class RankedCandidate:
    record: Record
    score: float


@dataclass
class DigestInput:
    review_name: str
    run_date: str                          # ISO date this run started
    source_counts: dict[str, int]          # records returned per source
    n_after_dedupe: int
    n_prior_decisions: int
    n_prior_included: int
    calibration: dict[float, float | None]  # recall target -> screen fraction
    ranked: list[RankedCandidate] = field(default_factory=list)
    reimport_path: str | None = None       # RIS file written this run


def render_markdown(d: DigestInput) -> str:
    lines: list[str] = []
    lines.append(f"# Living review update — {d.review_name}")
    lines.append(f"_Run date: {d.run_date}_")
    lines.append("")
    lines.append(SAFETY_NOTICE)
    lines.append("")

    lines.append("## What was found")
    for source, n in d.source_counts.items():
        lines.append(f"- {source}: {n} record(s) returned")
    total = sum(d.source_counts.values())
    n_dupes = total - d.n_after_dedupe
    lines.append(
        f"- **{d.n_after_dedupe} new candidate(s)** after removing {n_dupes} "
        "duplicate(s) / already-seen record(s)"
    )
    lines.append("")

    if d.n_after_dedupe == 0:
        lines.append("No new candidates this run — nothing to screen.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Screening effort vs. recall (calibrated on your prior decisions)")
    lines.append(
        f"_Basis: {d.n_prior_decisions} prior decisions "
        f"({d.n_prior_included} included), out-of-fold cross-validation._"
    )
    if d.n_prior_included < MIN_INCLUDED_FOR_CONFIDENT_CALIBRATION:
        lines.append("")
        lines.append(
            f"> **Low-confidence calibration.** With only {d.n_prior_included} "
            "included records, each one moves the estimate by "
            f"{1 / max(d.n_prior_included, 1):.0%} of total recall, so these "
            "numbers are coarse and the targets may collapse to the same "
            "figure. Treat them as a rough hint, not a stopping rule — screen "
            "the full list until you have "
            f"{MIN_INCLUDED_FOR_CONFIDENT_CALIBRATION}+ included records to "
            "calibrate on."
        )
    lines.append("")
    lines.append("| Target recall | Estimated fraction of ranked list to screen |")
    lines.append("|---|---|")
    for target in sorted(d.calibration):
        frac = d.calibration[target]
        cell = f"{frac:.0%}" if frac is not None else "n/a (too few decisions)"
        lines.append(f"| {target:.0%} | {cell} |")
    lines.append("")

    lines.append(f"## Ranked new candidates ({d.n_after_dedupe})")
    if d.reimport_path:
        lines.append(
            f"_Also written to `{d.reimport_path}` (RIS, in this order) for "
            "re-import into ASReview or a reference manager._"
        )
    lines.append("")
    for i, c in enumerate(d.ranked, start=1):
        r = c.record
        ids = " · ".join(x for x in (r.doi, r.source_id) if x)
        suffix = f" ({ids})" if ids else ""
        lines.append(f"{i}. [{c.score:.3f}] {r.title}{suffix}")
    lines.append("")
    return "\n".join(lines)
