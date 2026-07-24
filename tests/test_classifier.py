"""Fast, deterministic tests for the core relevance mechanic."""
from livingreview import RelevanceRanker, screen_fraction_for_recall


def _toy_corpus():
    # Included records are about "intravenous magnesium for asthma"; excluded
    # records are unrelated. A ranker trained on prior decisions should float
    # new on-topic records to the top.
    included = [
        ("Intravenous magnesium sulfate in acute severe asthma", "A trial of IV magnesium for asthma exacerbations."),
        ("Nebulized magnesium for asthma in the emergency department", "Magnesium therapy reduced admissions in asthma."),
        ("Magnesium sulfate for bronchospasm", "IV magnesium improved lung function in asthmatic adults."),
    ]
    excluded = [
        ("Hip replacement outcomes in elderly patients", "Arthroplasty recovery times were measured."),
        ("Coffee consumption and cardiovascular risk", "A cohort study of coffee and heart disease."),
        ("Soil microbiome diversity in temperate forests", "We sequenced soil bacterial communities."),
        ("Machine translation for low-resource languages", "Neural MT was evaluated across languages."),
    ]
    titles = [t for t, _ in included + excluded]
    abstracts = [a for _, a in included + excluded]
    labels = [1] * len(included) + [0] * len(excluded)
    return titles, abstracts, labels


def test_ranks_relevant_new_records_first():
    titles, abstracts, labels = _toy_corpus()
    ranker = RelevanceRanker().fit(titles, abstracts, labels)

    new_titles = [
        "Bicycle helmet legislation and injury rates",              # off-topic
        "Intravenous magnesium in pediatric asthma exacerbation",   # on-topic
        "A survey of container orchestration tools",                # off-topic
    ]
    new_abstracts = [
        "Helmet laws and their effect on head injuries.",
        "IV magnesium reduced hospitalization in children with asthma.",
        "We compared Kubernetes and Nomad.",
    ]
    ranked = ranker.rank(new_titles, new_abstracts)
    # The on-topic record (index 1) should be ranked first.
    assert ranked[0].index == 1
    assert ranked[0].score > ranked[-1].score


def test_screen_fraction_for_recall_monotonic():
    # Perfectly-ranked list: all positives first -> tiny screening for full recall.
    labels_best = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    assert screen_fraction_for_recall(labels_best, 1.0) == 0.2
    # Worst case: positives last -> must screen everything.
    labels_worst = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
    assert screen_fraction_for_recall(labels_worst, 1.0) == 1.0
    # No positives -> undefined (None).
    assert screen_fraction_for_recall([0, 0, 0], 0.95) is None
