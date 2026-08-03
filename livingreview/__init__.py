"""Living Review Updater — keep a systematic review current without re-screening
everything by hand. Ranks/flags new studies for human review; never auto-excludes.
"""
__version__ = "0.1.0"

from .classifier import (
    RelevanceRanker,
    RankedRecord,
    recall_at_screened,
    screen_fraction_for_recall,
)

__all__ = [
    "RelevanceRanker",
    "RankedRecord",
    "recall_at_screened",
    "screen_fraction_for_recall",
]
