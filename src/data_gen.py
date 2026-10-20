"""Synthetic data for AML-Nexus. SYNTHETIC ONLY - no real customers or real transactions.

Three kinds of accounts:
  (a) legitimate but suspicious-looking: shops, charities, payroll, friend-group cycles
  (b) planted laundering: fan-in rings, 'stealth' fan-in, closed loops
  (c) ordinary background noise
"""
import numpy as np
import pandas as pd

THRESHOLD = 10_000  # illustrative reporting threshold
DAYS = 90


def generate(seed: int = 7):
    rng = np.random.default_rng(seed)
    A, X, opened = [], [], {}

    def acct(i, op, label, role):
        opened[i] = int(op)
        A.append(dict(account=i, opened_day=int(op), label=label, role=role))

    def tx(s, d, amt, day):
        X.append(dict(src=str(s), dst=str(d), amount=round(float(amt), 2), day=int(day)))

    def pick(seq):
        return seq[int(rng.integers(len(seq)))]

    ext = [f"EXT{i:02d}" for i in range(8)]
    for e in ext:
        acct(e, -1000, "external", "outside_bank")
    old = [f"C{i:04d}" for i in range(500)]
    new = [f"NEW{i:03d}" for i in range(80)]
    for a in old:
        acct(a, -rng.integers(120, 3000), "normal", "customer")
    for a in new:
        acct(a, rng.integers(5, 80), "normal", "newcomer")

    def customer(day, p_new):
        pool = [n for n in new if opened[n] <= day]
        return pick(pool) if pool and rng.random() < p_new else pick(old)

    # (c) background noise
    for _ in range(2500):
        s, d = map(str, rng.choice(old + new, 2, replace=False))
        lo = max(opened[s], opened[d], 0)
        tx(s, d, min(rng.lognormal(5, 1), 7000), rng.integers(lo, DAYS))

    # (a) legitimate hubs
    for i in range(6):  # shops: many small deposits, mostly repeat customers
        sid = f"SHOP{i}"
        acct(sid, -rng.integers(200, 2000), "legit_hub", "shop")
        regulars = [str(x) for x in rng.choice(old, 40, replace=False)]
        for day in range(DAYS):
            for _ in range(rng.poisson(4)):
                snd = customer(day, 0.4) if rng.random() < 0.45 else pick(regulars)
                tx(snd, sid, min(rng.lognormal(3.8, 0.6), 600), day)
            if day % 7 == 6:
                tx(sid, pick(ext), rng.lognormal(6.3, 0.3), day)
    for i in range(3):  # charities: campaign burst, mostly one-time/new donors
        cid = f"CHARITY{i}"
        acct(cid, -rng.integers(300, 2500), "legit_hub", "charity")
        start, raised = int(rng.integers(20, 60)), 0.0
        for day in range(start, start + 3):
            for _ in range(int(rng.integers(40, 70))):
                amt = float(np.clip(rng.lognormal(4.2, 0.7), 5, 800))
                raised += amt
                tx(customer(day, 0.6), cid, amt, day)
        tx(cid, pick(ext), 0.85 * raised, start + 10)
    for i in range(2):  # payroll: fan-out, not fan-in
        pid = f"PAYROLL{i}"
        acct(pid, -1500, "legit_hub", "payroll")
        for day in (30, 60):
            for s in [str(x) for x in rng.choice(old, 40, replace=False)]:
                tx(pid, s, rng.uniform(1500, 3500), day)
    for c in range(3):  # friends splitting bills: a benign closed loop
        nodes = [f"FR{c}_{i}" for i in range(3)]
        for n in nodes:
            acct(n, -rng.integers(300, 2000), "normal", "friend_cycle")
        day = int(rng.integers(15, 60))
        for i in range(3):
            tx(nodes[i], nodes[(i + 1) % 3], rng.uniform(20, 200), day)
            day += int(rng.integers(1, 6))

    # (b) planted laundering
    for r in range(6):  # typical fan-in: many new accounts, just under threshold, fast forward
        start, col, total = int(rng.integers(20, 70)), f"COL{r}", 0.0
        acct(col, start - rng.integers(3, 15), "laundering", "collector")
        for j in range(int(rng.integers(15, 31))):
            m = f"MULE{r}_{j}"
            acct(m, start - rng.integers(1, 10), "laundering", "mule")
            for _ in range(int(rng.integers(1, 3))):
                amt = rng.uniform(0.85, 0.99) * THRESHOLD
                total += amt
                tx(m, col, amt, start + rng.integers(0, 5))
        tx(col, pick(ext), 0.9 * total, start + 5 + rng.integers(0, 2))
    for r in range(2):  # stealth fan-in: mixed senders, varied amounts, partial pass-through
        start, col, total = int(rng.integers(20, 70)), f"STL{r}", 0.0
        acct(col, start - rng.integers(3, 15), "laundering", "stealth_collector")
        for j in range(14):
            if j < 6:
                m = f"SMULE{r}_{j}"
                acct(m, start - rng.integers(1, 10), "laundering", "mule")
            else:
                m = pick(old)
            amt = rng.uniform(0.3, 0.95) * THRESHOLD
            total += amt
            tx(m, col, amt, start + rng.integers(0, 6))
        tx(col, pick(ext), 0.45 * total, start + 7)
    for c in range(4):  # closed loops with small skim per hop
        L, start = int(rng.integers(3, 6)), int(rng.integers(20, 65))
        nodes = [f"LC{c}_{i}" for i in range(L)]
        for n in nodes:
            acct(n, start - rng.integers(5, 20), "laundering", "cycle_member")
        amt, day = rng.uniform(5000, 40000), start
        for i in range(L):
            tx(nodes[i], nodes[(i + 1) % L], amt, day)
            amt *= rng.uniform(0.96, 0.995)
            day += int(rng.integers(0, 2))

    accounts = pd.DataFrame(A)
    txs = pd.DataFrame(X).sort_values("day", kind="stable").reset_index(drop=True)
    return accounts, txs
