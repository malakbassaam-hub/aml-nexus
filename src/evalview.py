"""Reads the saved evaluation files so the dashboard shows the same numbers as the README (no numbers are typed in by hand)."""
import json
from pathlib import Path
import pandas as pd

DOCS = Path(__file__).resolve().parent.parent / "docs"
KNOWN_LIMITS = ["All data is synthetic; nothing here is evidence about a real person.",
                "Scores are hand-set policy parameters, not validated limits. The statistical model was trained on synthetic data and shares the rules' features.",
                "Rings that use aged accounts are mostly missed; detection of evasive rings is sensitive to one threshold.",
                "A genuine fast-payout fundraiser can still reach Monitor: a human must verify."]


def load():
    out = {}
    for name in ("results", "ledger_results"):
        try:
            with open(DOCS / f"{name}.json") as f:
                out[name] = json.load(f)
        except (OSError, ValueError):
            out[name] = None
    return out


def headline(res):
    """Rows comparing AML-Nexus with the naive rule at matched detection, plus the effect of counter-evidence."""
    h, g = res["heldout_chosen"], res["heldout_no_gating"]
    return pd.DataFrame([
        ("Planted laundering found (mean)", f"{h['recall']:.1%}", f"{h['base_recall']:.1%}"),
        ("Worst single run", f"{h['recall_min']:.1%}", "n/a"),
        ("Innocent accounts escalated (freeze-level review)", f"{h['inn_escalate']:.1f}", "n/a"),
        ("Innocent accounts sent to Verify (contact only)", f"{h['inn_verify']:.1f}", "n/a"),
        ("Innocent accounts sent to Monitor", f"{h['inn_monitor']:.1f}", "n/a"),
        ("Innocent accounts flagged by the naive rule at matched detection", "n/a", f"{h['base_inn']:.1f}"),
        ("Runs where the naive rule could not reach our detection rate", "n/a", f"{h['baseline_could_not_match']} of 10"),
    ], columns=["Per held-out run (synthetic)", "AML-Nexus", "Naive count rule"])


def counter_evidence_effect(res):
    h, g = res["heldout_chosen"], res["heldout_no_gating"]
    return pd.DataFrame([("With counter-evidence", h["inn_verify"], h["inn_monitor"], h["recall"]),
                         ("Ignoring counter-evidence", g["inn_verify"], g["inn_monitor"], g["recall"])],
                        columns=["Setting", "Innocents at Verify", "Innocents at Monitor", "Planted laundering found"])


def per_seed(res):
    return pd.DataFrame(res["heldout_per_seed"])[["seed", "recall", "inn_verify", "inn_monitor", "inn_escalate", "base_inn"]].set_index("seed")


def sensitivity(res):
    """How the counter-evidence cut-off trades missed laundering against innocents under watch (development runs only)."""
    rows = [dict(cutoff=("no gating" if float(k) > 1 else k), recall=v["recall"], innocents_at_monitor=v["inn_monitor"], innocents_at_verify=v["inn_verify"])
            for k, v in res["dev_grid"].items()]
    return pd.DataFrame(rows).set_index("cutoff")


def ledger_summary(lres):
    c = lres["heldout_counts"]
    return dict(positives=c["pos"], negatives=c["neg"], model_found=c["nb_tp"], model_false=c["nb_fp"], rules_found=c["rule_tp"], rules_false=c["rule_fp"],
                both=c["both_tp"] + c["both_fp"], threshold=lres["threshold_db"])
