#!/usr/bin/env python3
"""
Retrospective backtest of the Living Review Updater's core mechanic.

Question that decides GO/NO-GO: if a review team has already screened a batch of
records (include/exclude decisions), can a classifier trained on THOSE decisions
rank the relevant studies in a *new* batch highly enough that the team catches
(almost) all of them while screening far fewer records?

We simulate a living-review "update" using real labeled SR data (SYNERGY): for
each review, train on a stratified 50% ("already screened") and measure, on the
held-out 50% ("newly arrived records"), how much screening you can SAFELY skip.

Key safety metric = recall. The tool must be recall-first: we report how much of
the new batch you must screen (in ranked order) to catch 95% and 100% of the
truly-relevant new studies. High work-saved AT high recall => it helps and is
safe. If you must screen ~everything to catch the includes, it does not help.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
from synergy_dataset import iter_datasets
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split

SEED = 42

def screen_fraction_for_recall(y_true_ranked, target_recall):
    """Given test labels sorted by model score (desc), fraction of records that
    must be screened (from the top) to reach target_recall of the positives."""
    total_pos = int(y_true_ranked.sum())
    if total_pos == 0:
        return None
    needed = int(np.ceil(target_recall * total_pos))
    cum = np.cumsum(y_true_ranked)
    idx = np.argmax(cum >= needed)  # first index where we've caught 'needed' positives
    return (idx + 1) / len(y_true_ranked)

def run_one(df):
    df = df.copy()
    df["text"] = (df["title"].fillna("") + ". " + df["abstract"].fillna("")).str.strip()
    df = df[df["text"].str.len() > 3]
    y = df["label_included"].astype(int).values
    if y.sum() < 6 or (len(y) - y.sum()) < 6:
        return None  # too few includes/excludes to split meaningfully
    Xtr_txt, Xte_txt, ytr, yte = train_test_split(
        df["text"].values, y, test_size=0.5, stratify=y, random_state=SEED
    )
    if yte.sum() == 0:
        return None
    vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=50000)
    Xtr = vec.fit_transform(Xtr_txt)
    Xte = vec.transform(Xte_txt)
    clf = MultinomialNB()
    clf.fit(Xtr, ytr)
    scores = clf.predict_proba(Xte)[:, 1]
    order = np.argsort(-scores)
    yte_ranked = yte[order]
    f95 = screen_fraction_for_recall(yte_ranked, 0.95)
    f100 = screen_fraction_for_recall(yte_ranked, 1.0)
    # WSS@95 = work saved vs screening everything, beyond the random baseline
    wss95 = (1 - f95) - 0.05 if f95 is not None else None
    return {
        "n_test": len(yte),
        "pos_test": int(yte.sum()),
        "prevalence": yte.sum() / len(yte),
        "screen_for_95": f95,
        "screen_for_100": f100,
        "wss95": wss95,
    }

def main():
    rows = []
    for d in iter_datasets():
        try:
            df = d.to_frame()
        except Exception:
            continue
        if not {"title", "abstract", "label_included"}.issubset(df.columns):
            continue
        res = run_one(df)
        if res:
            res["name"] = d.name
            rows.append(res)

    rows.sort(key=lambda r: r["wss95"] if r["wss95"] is not None else -1, reverse=True)
    print(f"{'review':<34}{'nTest':>7}{'pos':>5}{'prev':>7}{'screen@95%':>12}{'screen@100%':>13}{'WSS@95':>9}")
    print("-" * 90)
    for r in rows:
        print(f"{r['name'][:33]:<34}{r['n_test']:>7}{r['pos_test']:>5}{r['prevalence']*100:>6.1f}%"
              f"{r['screen_for_95']*100:>11.1f}%{r['screen_for_100']*100:>12.1f}%{r['wss95']*100:>8.1f}%")
    print("-" * 90)
    import statistics as st
    wss = [r["wss95"] for r in rows]
    s95 = [r["screen_for_95"] for r in rows]
    s100 = [r["screen_for_100"] for r in rows]
    print(f"{'MEDIAN across ' + str(len(rows)) + ' reviews':<34}{'':>7}{'':>5}{'':>7}"
          f"{st.median(s95)*100:>11.1f}%{st.median(s100)*100:>12.1f}%{st.median(wss)*100:>8.1f}%")
    print(f"{'MEAN':<34}{'':>7}{'':>5}{'':>7}"
          f"{st.mean(s95)*100:>11.1f}%{st.mean(s100)*100:>12.1f}%{st.mean(wss)*100:>8.1f}%")
    print()
    print("Read: 'screen@95%' = % of NEW records a human must screen (in ranked order)")
    print("to catch 95% of the truly-relevant new studies. Lower = more work saved.")
    print("WSS@95 = work saved at 95% recall beyond random. Higher = better & safe.")
    print("Baseline (no tool) = screen 100% to catch 100%.")

if __name__ == "__main__":
    main()
