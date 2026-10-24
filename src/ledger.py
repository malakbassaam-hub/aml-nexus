"""Evidence ledger: a small statistical model (naive Bayes with Laplace smoothing) whose every input adds or subtracts
'weight of evidence' in decibans (10*log10 of a likelihood ratio), in the spirit of I. J. Good's and Alan Turing's wartime work.
It sees the SAME features as the hand-written rules but learns the weights from synthetic training data, so it is a second
opinion with different weights, NOT independent evidence. It never outputs a probability: the prior of real life is unknown.
Not applicable to closed loops (the training data has no innocent loops)."""
import json
import math

LABELS = {
    "senders": ["<8", "8-14", "15-24", "25+"],
    "new_accounts": ["<20%", "20-50%", "50-90%", "90%+"],
    "structuring": ["none", "<30%", "30-80%", "80%+"],
    "pass_through": ["<10%", "10-40%", "40-80%", "80%+", "not yet observable"],
    "repeat": ["none", "<30%", "30-60%", "60%+"],
    "large_payments": ["<10%", "10-50%", "50%+"],
    "benford": ["typical", "above 75% of peers", "above 95% of peers", "insufficient data"],
    "pattern": ["fan_in", "slow_accumulation"],
}
TITLES = {"senders": "Distinct senders", "new_accounts": "Senders that are new accounts", "structuring": "Deposits just under the threshold",
          "pass_through": "Share moved out quickly", "repeat": "Senders already known to the account", "large_payments": "Large individual payments",
          "benford": "First-digit pattern (Benford) vs peers", "pattern": "Pattern type"}


def _b(x, edges):
    return next((i for i, e in enumerate(edges) if x < e), len(edges))


def bin_features(row_features, kind, benford_pct=None):
    f = row_features
    return {"senders": LABELS["senders"][_b(f["n_senders"], [8, 15, 25])],
            "new_accounts": LABELS["new_accounts"][_b(f["new_share"], [0.2, 0.5, 0.9])],
            "structuring": LABELS["structuring"][0 if f["struct"] == 0 else 1 + _b(f["struct"], [0.3, 0.8])],
            "pass_through": LABELS["pass_through"][4 if f["unobs"] else _b(f["pas"], [0.1, 0.4, 0.8])],
            "repeat": LABELS["repeat"][0 if f["repeat"] == 0 else 1 + _b(f["repeat"], [0.3, 0.6])],
            "large_payments": LABELS["large_payments"][_b(f["big"], [0.1, 0.5])],
            "benford": LABELS["benford"][3 if benford_pct is None else _b(benford_pct, [0.75, 0.95])],
            "pattern": kind}


def train(samples):
    """samples: list of (binned_features, is_laundering). Returns {feature: {label: decibans}}."""
    pos = [b for b, y in samples if y]
    neg = [b for b, y in samples if not y]
    model = {}
    for feat, labels in LABELS.items():
        k = len(labels)
        model[feat] = {}
        for lab in labels:
            p = (sum(b[feat] == lab for b in pos) + 1) / (len(pos) + k)
            n = (sum(b[feat] == lab for b in neg) + 1) / (len(neg) + k)
            model[feat][lab] = round(10 * math.log10(p / n), 2)
    return model


def score(model, binned):
    entries = [(feat, binned[feat], model[feat][binned[feat]]) for feat in LABELS]
    return round(sum(d for _, _, d in entries), 2), entries


def pick_threshold(model, samples):
    """Youden's J on the training data: the cut that best separates the two groups."""
    sc = [(score(model, b)[0], y) for b, y in samples]
    npos, nneg = sum(y for _, y in sc), sum(not y for _, y in sc)
    best = max(sorted({s for s, _ in sc}), key=lambda t: sum(s >= t and y for s, y in sc) / npos - sum(s >= t and not y for s, y in sc) / nneg)
    return best


def save(path, model, threshold, meta):
    with open(path, "w") as f:
        json.dump(dict(model=model, threshold=threshold, **meta), f, indent=1)


def load(path):
    with open(path) as f:
        d = json.load(f)
    return d["model"], d["threshold"], d
