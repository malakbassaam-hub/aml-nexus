"""Train the evidence ledger on TRAIN seeds, choose its cut on TRAIN, report on HELD-OUT seeds.  Run: python -m src.train_ledger
Synthetic data only. The model sees the same features as the rules; this compares learned weights with hand-set weights."""
import json
from . import ledger
from .benford import peer_table
from .data_gen import generate
from .evaluate import HELD
from .risk import build_cases

TRAIN = list(range(11, 25))
POS = {"collector", "stealth_collector", "evasive_collector", "slow_collector"}


def rows_for(seed):
    acc, tx = generate(seed)
    role = acc.set_index("account")["role"].to_dict()
    label = acc.set_index("account")["label"].to_dict()
    peers = peer_table(tx, acc, int(tx.day.max()))
    cs = build_cases(tx, acc)
    out = []
    for r in cs[cs.kind.isin(["fan_in", "slow_accumulation"])].itertuples():
        y = role[r.account] in POS
        if not y and label[r.account] not in ("normal", "legit_hub"):
            continue
        pct = peers.get(r.account, {}).get("pct")
        out.append(dict(binned=ledger.bin_features(r.features, r.kind, pct), y=y, rules=r.tier in ("Monitor", "Escalate"), role=role[r.account]))
    return out


def tally(rows, model, t):
    c = dict(pos=0, neg=0, nb_tp=0, nb_fp=0, rule_tp=0, rule_fp=0, both_tp=0, both_fp=0, rules_only_tp=0, rules_only_fp=0, model_only_tp=0, model_only_fp=0)
    for r in rows:
        nb = ledger.score(model, r["binned"])[0] >= t
        k = "tp" if r["y"] else "fp"
        c["pos" if r["y"] else "neg"] += 1
        c["nb_" + k] += nb
        c["rule_" + k] += r["rules"]
        c["both_" + k] += nb and r["rules"]
        c["rules_only_" + k] += r["rules"] and not nb
        c["model_only_" + k] += nb and not r["rules"]
    return c


if __name__ == "__main__":
    train_rows = [r for s in TRAIN for r in rows_for(s)]
    samples = [(r["binned"], r["y"]) for r in train_rows]
    model = ledger.train(samples)
    t = ledger.pick_threshold(model, samples)
    held_rows = [r for s in HELD for r in rows_for(s)]
    res = dict(train_seeds=TRAIN, heldout_seeds=HELD, threshold_db=t, train_counts=tally(train_rows, model, t), heldout_counts=tally(held_rows, model, t),
               note="Same features as the rules; learned weights vs hand-set weights. Closed loops are excluded (no innocent loops in the data).")
    print(json.dumps(res["heldout_counts"], indent=1)); print("threshold (dB):", t, "| train:", res["train_counts"])
    ledger.save("docs/ledger_model.json", model, t, dict(train_seeds=TRAIN, n_train=len(train_rows)))
    json.dump(res, open("docs/ledger_results.json", "w"), indent=1)
    for f, d in model.items():
        print(f"{f:15s}", {k: v for k, v in d.items()})
