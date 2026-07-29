"""Write new candidate records as an RIS file for re-import into ASReview
(or any reference manager). Records are written in ranked order — most likely
relevant first — which ASReview preserves, so a team screening top-down gets
the ranking's benefit even inside their existing tool.
"""
from __future__ import annotations

from pathlib import Path

from .dedupe import Record


def _clean(text: str) -> str:
    # RIS is line-oriented: a newline inside a value would break the record.
    return " ".join((text or "").split())


def write_ris(records: list[Record], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for r in records:
        lines.append("TY  - JOUR")
        lines.append(f"TI  - {_clean(r.title)}")
        if r.abstract:
            lines.append(f"AB  - {_clean(r.abstract)}")
        if r.doi:
            lines.append(f"DO  - {_clean(r.doi)}")
        if r.source_id:
            lines.append(f"ID  - {_clean(r.source_id)}")
        lines.append("ER  - ")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
