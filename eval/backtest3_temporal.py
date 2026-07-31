#!/usr/bin/env python3
"""
Temporal backtest of the Living Review Updater's core mechanic.

The gate-passing backtest (backtest2.py / backtest-RESULTS.md) used a RANDOM
stratified 80/20 split. Real living-review updates are not random: the team has
screened everything published up to some date, and the update delivers records
published AFTER that date. Terminology drift, topic drift, and new study types
can make ranking of *future* records worse than a random split suggests.

This script runs BOTH splits on identical data per review:
  - RANDOM:   stratified 80/20 (the original protocol, as a control)
  - TEMPORAL: train on the earliest ~80% of records by publication date,
              test on the latest ~20% (a true original->update simulation)

Same features (TF-IDF 1-2grams), same models (MultinomialNB vs balanced
LogisticRegression, best-of-two by screen@95 on the test set), same metrics
(screen@95, screen@100, WSS@95) as backtest2.py, so any difference is
attributable to the split, not the protocol.

Data: SYNERGY 1.0 works_*.zip files (OpenAlex records), which carry
publication_date / publication_year for every record. Abstracts are
reconstructed from OpenAlex abstract_inverted_index.
"""
import warnings
warnings.filterwarnings("ignore")

import csv
import glob
import json
import os
import statistics as st
import zipfile

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB

SEED = 42
SOURCE_DIR = os.path.expanduser("~/.synergy_dataset_source/synergy-dataset-1.0")
TEST_FRAC = 0.2


def invert_abstract(inv):
    """Rebuild abstract text from an OpenAlex abstract_inverted_index."""
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def load_review(path):
    """Return list of dicts: {text, label, date} for one SYNERGY review."""
    labels = {}
    with open(os.path.join(path, "labels.csv")) as f:
        for row in csv.DictReader(f):
            labels[row["openalex_id"]] = int(row["label_included"])
    records = []
    for zpath in sorted(glob.glob(os.path.join(path, "works_*.zip"))):
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for rec in json.load(f):
                        oid = rec.get("id")
                        if oid not in labels:
                            continue
                        title = rec.get("title") or ""
                        abstract = invert_abstract(rec.get("abstract_inverted_index"))
                        text = (title + ". " + abstract).strip()
                        if len(text) <= 3:
                            continue
                        date = rec.get("publication_date") or (
                            f"{rec['publication_year']}-01-01" if rec.get("publication_year") else None
                        )
                        if date is None:
                            continue  # can't place undated records on a timeline
                        records.append({"text": text, "label": labels[oid], "date": date})
    return records


def screen_fraction_for_recall(y_true_ranked, target_recall):
    total_pos = int(y_true_ranked.sum())
    if total_pos == 0:
        return None
    needed = int(np.ceil(target_recall * total_pos))
    cum = np.cumsum(y_true_ranked)
    idx = np.argmax(cum >= needed)
    return (idx + 1) / len(y_true_ranked)


def rank_and_score(Xtr_txt, ytr, Xte_txt, yte):
    """Original backtest2 protocol: TF-IDF + best of NB/LR by screen@95."""
    if yte.sum() == 0 or ytr.sum() == 0:
        return None
    vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=50000)
    Xtr = vec.fit_transform(Xtr_txt)
    Xte = vec.transform(Xte_txt)
    best = None
    for name, clf in [("NB", MultinomialNB()),
                      ("LR", LogisticRegression(class_weight="balanced", max_iter=2000, C=10))]:
        clf.fit(Xtr, ytr)
        sc = clf.predict_proba(Xte)[:, 1]
        order = np.argsort(-sc)
        f95 = screen_fraction_for_recall(yte[order], 0.95)
        if best is None or (f95 is not None and f95 < best[0]):
            best = (f95, name, sc)
    f95, model_name, scores = best
    order = np.argsort(-scores)
    yte_ranked = yte[order]
    f95 = screen_fraction_for_recall(yte_ranked, 0.95)
    f100 = screen_fraction_for_recall(yte_ranked, 1.0)
    return {
        "n_test": len(yte),
        "pos_test": int(yte.sum()),
        "screen_for_95": f95,
        "screen_for_100": f100,
        "wss95": (1 - f95) - 0.05 if f95 is not None else None,
        "model": model_name,
    }


def run_review(records):
    texts = np.array([r["text"] for r in records])
    y = np.array([r["label"] for r in records], dtype=int)
    dates = np.array([r["date"] for r in records])
    if y.sum() < 6 or (len(y) - y.sum()) < 6:
        return None

    # RANDOM control (original protocol)
    Xtr_txt, Xte_txt, ytr, yte = train_test_split(
        texts, y, test_size=TEST_FRAC, stratify=y, random_state=SEED
    )
    random_res = rank_and_score(Xtr_txt, ytr, Xte_txt, yte)

    # TEMPORAL split: train on earliest ~80% by publication date, test on latest ~20%.
    # Cutoff is a date boundary (all records sharing the cutoff date go to train),
    # because a real update cursor is a date, not a row count.
    order = np.argsort(dates, kind="stable")
    cut_idx = int(np.floor(len(dates) * (1 - TEST_FRAC)))
    cutoff_date = dates[order][min(cut_idx, len(dates) - 1)]
    train_mask = dates < cutoff_date
    test_mask = ~train_mask
    # Degenerate cutoffs (many records share one date) -> fall back to row split
    if train_mask.sum() < 10 or test_mask.sum() < 5:
        train_idx, test_idx = order[:cut_idx], order[cut_idx:]
        train_mask = np.zeros(len(y), bool); train_mask[train_idx] = True
        test_mask = ~train_mask
        cutoff_date = dates[order][cut_idx] + " (row-split fallback)"
    temporal_res = rank_and_score(texts[train_mask], y[train_mask],
                                  texts[test_mask], y[test_mask])
    return {
        "random": random_res,
        "temporal": temporal_res,
        "cutoff": cutoff_date,
        "n": len(y),
        "pos_total": int(y.sum()),
        "train_pos": int(y[train_mask].sum()),
    }


def fmt(res, key):
    if res is None or res.get(key) is None:
        return "     n/a"
    return f"{res[key]*100:7.1f}%"


def main():
    rows = []
    skipped = []
    for path in sorted(glob.glob(os.path.join(SOURCE_DIR, "*"))):
        if not os.path.isdir(path):
            continue
        name = os.path.basename(path)
        records = load_review(path)
        out = run_review(records)
        if out is None:
            skipped.append(name)
            continue
        out["name"] = name
        rows.append(out)

    print(f"{'review':<28}{'cutoff':>12}{'nPosTr':>7} | {'rnd@95':>8}{'rnd WSS':>8} | "
          f"{'tmp@95':>8}{'tmp WSS':>8}{'tmpPos':>7}  note")
    print("-" * 110)
    for r in rows:
        tr, tp = r["random"], r["temporal"]
        note = ""
        if tp is None:
            note = "no includes in temporal test window" if r["train_pos"] == r["pos_total"] \
                else "no includes in train window"
        cutoff = r["cutoff"][:10]
        print(f"{r['name'][:27]:<28}{cutoff:>12}{r['train_pos']:>7} | "
              f"{fmt(tr,'screen_for_95')}{fmt(tr,'wss95')} | "
              f"{fmt(tp,'screen_for_95')}{fmt(tp,'wss95')}"
              f"{tp['pos_test'] if tp else 0:>7}  {note}")
    print("-" * 110)

    both = [r for r in rows if r["random"] and r["temporal"]]
    for label, key in [("screen@95", "screen_for_95"), ("WSS@95", "wss95"), ("screen@100", "screen_for_100")]:
        rnd = [r["random"][key] for r in both if r["random"][key] is not None]
        tmp = [r["temporal"][key] for r in both if r["temporal"][key] is not None]
        print(f"MEDIAN {label:<11} random: {st.median(rnd)*100:6.1f}%   temporal: {st.median(tmp)*100:6.1f}%   "
              f"(n={len(both)} reviews with includes in both test sets)")
    deltas = [r["temporal"]["wss95"] - r["random"]["wss95"] for r in both
              if r["random"]["wss95"] is not None and r["temporal"]["wss95"] is not None]
    print(f"MEDIAN per-review WSS@95 delta (temporal - random): {st.median(deltas)*100:+.1f} pts; "
          f"mean {st.mean(deltas)*100:+.1f} pts")
    worse = sum(1 for d in deltas if d < -0.05)
    print(f"Reviews where temporal is >5 pts worse: {worse}/{len(deltas)}")
    no_test_pos = [r["name"] for r in rows if r["temporal"] is None]
    if no_test_pos:
        print(f"Excluded from medians (no includes in one window): {', '.join(no_test_pos)}")
    if skipped:
        print(f"Skipped (too few includes/excludes or no dates): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
