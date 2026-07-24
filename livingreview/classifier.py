"""
Relevance classifier for the Living Review Updater.

Core mechanic (validated by eval/backtest2.py on 26 real SYNERGY reviews:
median ~84% screening work saved at 95% recall): train on a review team's OWN
prior include/exclude decisions, then RANK newly-found records so a human
screens the most-likely-relevant ones first.

SAFETY CONTRACT — this module ranks and reports recall; it must NEVER be used to
auto-exclude. Callers surface a ranked list + a recall estimate to a human, who
remains accountable for inclusion decisions. See README "Design principles".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


def _texts(titles: Sequence[str], abstracts: Sequence[str]) -> list[str]:
    return [
        f"{(t or '').strip()}. {(a or '').strip()}".strip()
        for t, a in zip(titles, abstracts)
    ]


@dataclass
class RankedRecord:
    index: int
    score: float


class RelevanceRanker:
    """Trains on prior decisions; ranks new records by predicted relevance.

    Default model = TF-IDF (title+abstract, 1-2 grams) + class-balanced
    LogisticRegression. This beat Naive Bayes on 24/26 backtest reviews.
    """

    def __init__(self, max_features: int = 50_000):
        self.vectorizer = TfidfVectorizer(
            sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=max_features
        )
        self.model = LogisticRegression(
            class_weight="balanced", max_iter=2000, C=10
        )
        self._fitted = False

    def fit(self, titles, abstracts, included) -> "RelevanceRanker":
        """included: 1 = the team included this record, 0 = excluded."""
        y = np.asarray(included).astype(int)
        if y.sum() < 3 or (len(y) - y.sum()) < 3:
            raise ValueError(
                "Need at least 3 included and 3 excluded prior decisions to train."
            )
        X = self.vectorizer.fit_transform(_texts(titles, abstracts))
        self.model.fit(X, y)
        self._fitted = True
        return self

    def score(self, titles, abstracts) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit() before score().")
        X = self.vectorizer.transform(_texts(titles, abstracts))
        return self.model.predict_proba(X)[:, 1]

    def rank(self, titles, abstracts) -> list[RankedRecord]:
        scores = self.score(titles, abstracts)
        order = np.argsort(-scores)
        return [RankedRecord(index=int(i), score=float(scores[i])) for i in order]


def recall_at_screened(labels_in_rank_order: Sequence[int], fraction_screened: float) -> float:
    """Recall achieved if a human screens the top `fraction_screened` of the
    ranked list. Used to report the recall/effort trade-off honestly."""
    y = np.asarray(labels_in_rank_order).astype(int)
    total_pos = int(y.sum())
    if total_pos == 0:
        return 1.0
    k = max(1, int(round(fraction_screened * len(y))))
    return float(y[:k].sum()) / total_pos


def screen_fraction_for_recall(labels_in_rank_order: Sequence[int], target_recall: float) -> float | None:
    """Fraction of the ranked list a human must screen to reach target_recall.
    None if there are no positives. This is the number a digest reports so the
    team can choose where to stop screening for their required recall."""
    y = np.asarray(labels_in_rank_order).astype(int)
    total_pos = int(y.sum())
    if total_pos == 0:
        return None
    needed = int(np.ceil(target_recall * total_pos))
    cum = np.cumsum(y)
    idx = int(np.argmax(cum >= needed))
    return (idx + 1) / len(y)
