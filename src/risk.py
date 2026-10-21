"""Turns detector output into cases with a recommended tier. The system only RECOMMENDS; a human decides."""
import pandas as pd
from .detectors import fan_in_scan, find_cycles, _opened

PARAMS = {"c_mon": 0.35}  # policy parameter: Monitor needs counter-evidence below this; chosen on DEV seeds only (see evaluate.py)


def recommend(s, c, c_mon=None):
    """s = suspicion (0-1), c = counter-evidence (0-1). Tiers: Clear / Verify / Monitor (Evidence Watch) / Escalate."""
    c_mon = PARAMS["c_mon"] if c_mon is None else c_mon
    if s >= 0.75 and c < 0.4:
        return "Escalate"
    if s >= 0.5:
        return "Monitor" if (c < c_mon or s >= 0.75) else "Verify"
    if s >= 0.35:
        return "Clear" if c >= 0.6 else "Verify"
    return "Clear"


def build_cases(tx, accounts, c_mon=None):
    rows, opened = [], _opened(accounts)
    fi = fan_in_scan(tx, accounts)
    if len(fi):
        rows += fi.to_dict("records")
    for cy in find_cycles(tx, accounts):
        est = sum((cy["start_day"] - opened[n]) > 180 for n in cy["nodes"]) / len(cy["nodes"])
        keep = min(b / a for a, b in zip(cy["amounts"], cy["amounts"][1:])) if len(cy["amounts"]) > 1 else 1
        for n in cy["nodes"]:
            rows.append(dict(account=n, kind="cycle", suspicion=0.85, counter=round(0.5 * est, 3),
                             supporting=[f"funds returned to origin through {len(cy['nodes'])} accounts in {cy['span']} days",
                                         f"each hop kept at least {keep:.0%} of the amount"],
                             counter_evidence=[f"{est:.0%} of loop members are long-standing accounts"] if est else []))
    if not rows:
        return pd.DataFrame(columns=["account", "kind", "suspicion", "counter", "supporting", "counter_evidence", "tier"])
    df = pd.DataFrame(rows).sort_values("suspicion", ascending=False).drop_duplicates("account")
    df["tier"] = [recommend(s, c, c_mon) for s, c in zip(df.suspicion, df.counter)]
    return df.reset_index(drop=True)
