"""Compare AML-Nexus with naive rules at MATCHED detection rate. Run: python -m src.evaluate
Results hold for the synthetic data only; they are NOT claims about real banks."""
import json
from .data_gen import generate
from .detectors import baseline_max_counts, baseline_cycle_members
from .risk import build_cases

POS = {"collector", "stealth_collector", "cycle_member"}


def run(seed=7):
    acc, tx = generate(seed)
    role = acc.set_index("account")["role"].to_dict()
    label = acc.set_index("account")["label"].to_dict()
    pos = {a for a, r in role.items() if r in POS}
    neg = {a for a, l in label.items() if l in ("normal", "legit_hub")}

    def score(flagged):
        f = flagged & (pos | neg)
        inn = f & neg
        by = {}
        for a in inn:
            by[role[a]] = by.get(role[a], 0) + 1
        return dict(recall=round(len(f & pos) / len(pos), 3), caught=len(f & pos), positives=len(pos),
                    innocents_flagged=len(inn), by_role=by)

    cases = build_cases(tx, acc)
    ours = score(set(cases[cases.tier.isin(["Monitor", "Escalate"])].account))
    ours_escalate_innocents = len(set(cases[cases.tier == "Escalate"].account) & neg)
    counts, cyc = baseline_max_counts(tx, acc), baseline_cycle_members(tx, acc)
    sweep = {k: score({a for a, c in counts.items() if c >= k} | cyc) for k in range(5, 61, 5)}
    ok = [k for k, v in sweep.items() if v["recall"] >= ours["recall"]]
    matched = max(ok) if ok else min(sweep)
    out = dict(seed=seed, ours=ours, ours_escalate_innocents=ours_escalate_innocents,
               baseline_matched_k=matched, baseline_at_matched=sweep[matched], baseline_sweep=sweep)
    return out, cases


if __name__ == "__main__":
    res, cases = run()
    print(json.dumps({k: v for k, v in res.items() if k != "baseline_sweep"}, indent=2))
    print("\nBaseline sweep (k = deposits in 7 days):")
    for k, v in res["baseline_sweep"].items():
        print(f"  k={k:>2}  recall={v['recall']:.2f}  innocents flagged={v['innocents_flagged']}")
    json.dump(res, open("docs/results.json", "w"), indent=2)
