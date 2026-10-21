"""AML-Nexus vs naive rules at MATCHED detection rate, over many synthetic seeds.
Calibration (the Monitor counter-evidence cutoff) uses DEV seeds only; results are reported on HELD-OUT seeds.
Everything here is synthetic. It is NOT a claim about real banks.   Run: python -m src.evaluate"""
import json
from statistics import mean
from .data_gen import generate
from .detectors import baseline_max_counts, baseline_cycle_members
from .risk import build_cases, recommend

POS = {"collector", "stealth_collector", "evasive_collector", "cycle_member"}
DEV, HELD = list(range(1, 5)), list(range(100, 110))
GRID = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 1.01]  # 1.01 = no counter-evidence gating (old behaviour)


def prep(seed):
    acc, tx = generate(seed)
    role = acc.set_index("account")["role"].to_dict()
    label = acc.set_index("account")["label"].to_dict()
    pos = {a for a, r in role.items() if r in POS}
    neg = {a for a, l in label.items() if l in ("normal", "legit_hub")}
    counts, cyc = baseline_max_counts(tx, acc), baseline_cycle_members(tx, acc)
    bl = {}
    for k in range(5, 61, 5):
        f = ({a for a, c in counts.items() if c >= k} | cyc) & (pos | neg)
        bl[k] = (len(f & pos) / len(pos), len(f & neg))
    return dict(seed=seed, role=role, pos=pos, neg=neg, cases=build_cases(tx, acc), bl=bl)


def metrics(p, c_mon):
    cs = p["cases"]
    tier = {a: recommend(s, c, c_mon) for a, s, c in zip(cs.account, cs.suspicion, cs.counter)}
    grp = lambda *t: {a for a, x in tier.items() if x in t}
    act, pos, neg = grp("Monitor", "Escalate"), p["pos"], p["neg"]
    recall = len(act & pos) / len(pos)
    ok = [k for k, (r, _) in p["bl"].items() if r >= recall]
    k = max(ok) if ok else min(p["bl"])
    return dict(recall=recall, inn_verify=len(grp("Verify") & neg), inn_monitor=len(grp("Monitor") & neg),
                inn_escalate=len(grp("Escalate") & neg), base_k=k, base_recall=p["bl"][k][0],
                base_inn=p["bl"][k][1], base_reached=bool(ok))


def summarize(rows):
    m = lambda key: round(mean(r[key] for r in rows), 3)
    return {k: m(k) for k in ("recall", "inn_verify", "inn_monitor", "inn_escalate", "base_recall", "base_inn")} | \
           {"recall_min": round(min(r["recall"] for r in rows), 3), "baseline_could_not_match": sum(not r["base_reached"] for r in rows)}


if __name__ == "__main__":
    dev, held = [prep(s) for s in DEV], [prep(s) for s in HELD]
    grid = {c: summarize([metrics(p, c) for p in dev]) for c in GRID}
    print("DEV calibration grid (c_mon: recall | innocents Monitor | Escalate):")
    for c, v in grid.items():
        print(f"  {c:>4}: {v['recall']:.3f} | {v['inn_monitor']:.1f} | {v['inn_escalate']:.1f}")
    safe = [c for c in GRID if grid[c]["inn_escalate"] == 0 and c < 1]
    best = max(safe, key=lambda c: (grid[c]["recall"], -grid[c]["inn_monitor"], -c))
    print("chosen c_mon =", best)
    res = dict(chosen_c_mon=best, dev_grid={str(c): v for c, v in grid.items()},
               heldout_chosen=summarize([metrics(p, best) for p in held]),
               heldout_no_gating=summarize([metrics(p, 1.01) for p in held]),
               heldout_per_seed=[dict(seed=p["seed"], **metrics(p, best)) for p in held])
    print(json.dumps({k: v for k, v in res.items() if k.startswith("heldout_") and k != "heldout_per_seed"}, indent=2))
    json.dump(res, open("docs/results.json", "w"), indent=2)
