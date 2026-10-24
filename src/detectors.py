"""Graph/pattern detectors + the rule-based baselines they are compared against."""
from collections import defaultdict
import networkx as nx
import numpy as np
import pandas as pd
from .data_gen import THRESHOLD

WIN, TAIL, WARMUP = 7, 3, 14  # first WARMUP days are treated as history only
SLOW_WIN, YOUNG_DAYS, SLOW_CAP = 30, 45, 0.74  # slow-accumulation typology can open a watch, never escalate alone


def _opened(accounts):
    return accounts.set_index("account")["opened_day"].to_dict()


def fan_in_scan(tx, accounts, min_senders=5, now=None):
    """Best 7-day window per receiving account, with evidence FOR and AGAINST."""
    opened, ext = _opened(accounts), set(accounts.loc[accounts.label == "external", "account"])
    now = (int(tx.day.max()) if len(tx) else 0) if now is None else now
    outs = {k: g for k, g in tx.groupby("src")}
    rows = []
    for a, inc in tx.groupby("dst"):
        if a in ext:
            continue
        o, best = outs.get(a), None
        for s in sorted(d for d in inc.day.unique() if d >= WARMUP):
            w = inc[(inc.day >= s) & (inc.day < s + WIN)]
            snd = w.groupby("src").day.min()
            if len(snd) < min_senders:
                continue
            new_share = float(np.mean([(d - opened[x]) < 30 for x, d in snd.items()]))
            prior = set(inc.loc[inc.day < s, "src"])
            repeat = float(np.mean([x in prior for x in snd.index]))
            struct = float(((w.amount >= 0.8 * THRESHOLD) & (w.amount < THRESHOLD)).mean())
            total_in = w.amount.sum()
            out = 0.0 if o is None else o[(o.day >= s) & (o.day < s + WIN + TAIL)].amount.sum()
            pas = min(out / total_in, 1.0)
            unobs = s + WIN + TAIL > now + 1  # money may simply not have moved yet: unknown, not exculpatory
            ret = 0.5 if unobs else (1 - pas)
            sus = 0.2 * min(len(snd) / 15, 1) + 0.25 * new_share + 0.25 * struct + 0.3 * pas
            if best is None or sus > best["suspicion"]:
                sup, cnt = [], []
                sup.append(f"{len(snd)} distinct senders within {WIN} days")
                if new_share >= 0.3: sup.append(f"{new_share:.0%} of senders opened <30 days before paying")
                if struct >= 0.3: sup.append(f"{struct:.0%} of deposits sit just under the {THRESHOLD:,} threshold")
                if pas >= 0.3: sup.append(f"{pas:.0%} of inflow moved out within {TAIL} days")
                if repeat >= 0.4: cnt.append(f"{repeat:.0%} of senders are established counterparties")
                if new_share <= 0.5: cnt.append(f"{1 - new_share:.0%} of senders are long-standing accounts")
                if pas <= 0.5 and not unobs: cnt.append(f"{1 - pas:.0%} of inflow was retained, not passed on")
                if struct < 0.1: cnt.append("deposit amounts are not clustered under the threshold")
                best = dict(account=a, kind="fan_in", suspicion=round(sus, 3),
                            counter=round(0.4 * repeat + 0.3 * (1 - new_share) + 0.3 * ret, 3),
                            supporting=sup, counter_evidence=cnt, window_start=int(s),
                            components=dict(breadth=round(0.2 * min(len(snd) / 15, 1), 3), new_accounts=round(0.25 * new_share, 3),
                                            structuring=round(0.25 * struct, 3), pass_through=round(0.3 * pas, 3)),
                            counter_components=dict(repeat=round(0.4 * repeat, 3), established=round(0.3 * (1 - new_share), 3),
                                                    retention=round(0.3 * ret, 3)),
                            notes=["Money movement is not yet observable for this window: counted as neutral, not as evidence of innocence."] if unobs else [])
        # slow accumulation into a young account: 30-day horizon, many senders, large tickets, funnel shape
        for s in sorted(d for d in inc.day.unique() if d >= WARMUP and d - opened[a] <= YOUNG_DAYS):
            w = inc[(inc.day >= s) & (inc.day < s + SLOW_WIN)]
            snd = w.groupby("src").day.min()
            total_in = w.amount.sum()
            if len(snd) < 8 or total_in < 2 * THRESHOLD:
                continue
            outw = None if o is None else o[(o.day >= s) & (o.day < s + SLOW_WIN + TAIL)]
            out = 0.0 if outw is None else outw.amount.sum()
            nrecv = 0 if outw is None else outw.dst.nunique()
            if len(snd) / max(1, nrecv) < 4:
                continue
            new_share = float(np.mean([(d - opened[x]) < 30 for x, d in snd.items()]))
            repeat = float(np.mean([x in set(inc.loc[inc.day < s, "src"]) for x in snd.index]))
            big = float((w.amount >= 0.15 * THRESHOLD).mean())
            pas = min(out / total_in, 1.0)
            unobs = s + SLOW_WIN + TAIL > now + 1
            ret = 0.5 if unobs else (1 - pas)
            raw = 0.3 + 0.25 * min(total_in / (4 * THRESHOLD), 1) + 0.25 * big + 0.2 * pas
            sus = min(raw, SLOW_CAP)
            if best is None or sus > best["suspicion"]:
                cnt = []
                if repeat >= 0.4: cnt.append(f"{repeat:.0%} of senders are established counterparties")
                if new_share <= 0.5: cnt.append(f"{1 - new_share:.0%} of senders are long-standing accounts")
                if pas <= 0.5 and not unobs: cnt.append(f"{1 - pas:.0%} of inflow was retained, not passed on")
                if big < 0.3: cnt.append("payments are mostly small, ordinary-sized tickets")
                best = dict(account=a, kind="slow_accumulation", suspicion=round(sus, 3),
                            counter=round(0.4 * repeat + 0.3 * (1 - new_share) + 0.3 * ret, 3),
                            supporting=[f"account opened {int(w.day.min() - opened[a])} days before this inflow began",
                                        f"{len(snd)} distinct senders paid {total_in:,.0f} within {SLOW_WIN} days",
                                        f"{big:.0%} of payments are large (>= {int(0.15 * THRESHOLD):,})",
                                        (f"funnel shape: {len(snd)} senders -> {nrecv} recipient(s)" if nrecv else f"funnel shape: {len(snd)} senders, no outflow observed yet")],
                            counter_evidence=cnt, window_start=int(s),
                            components=dict(typology=0.3, volume=round(0.25 * min(total_in / (4 * THRESHOLD), 1), 3), large_payments=round(0.25 * big, 3),
                                            pass_through=round(0.2 * pas, 3), cap=round(sus - raw, 3)),
                            counter_components=dict(repeat=round(0.4 * repeat, 3), established=round(0.3 * (1 - new_share), 3),
                                                    retention=round(0.3 * ret, 3)),
                            notes=["Money movement is not yet observable for this window: counted as neutral, not as evidence of innocence."] if unobs else [])
        if best:
            rows.append(best)
    return pd.DataFrame(rows)


def find_cycles(tx, accounts, max_len=5, win=7, keep_lo=0.85, min_amount=1000, amount_rule=True):
    """Closed loops that are time-ordered; with amount_rule each hop must pass on 85-100% of the amount."""
    edge = defaultdict(list)
    for r in tx.itertuples():
        if r.amount >= min_amount:
            edge[(r.src, r.dst)].append((r.day, r.amount))
    G = nx.DiGraph(list(edge))
    found = []
    for cyc in nx.simple_cycles(G, length_bound=max_len):
        if len(cyc) < 3:
            continue
        for k in range(len(cyc)):
            nodes = cyc[k:] + cyc[:k]
            hit = None
            for d0, a0 in sorted(edge[(nodes[0], nodes[1])]):
                prev_d, prev_a, path, ok = d0, a0, [a0], True
                for i in range(1, len(nodes)):
                    e = (nodes[i], nodes[(i + 1) % len(nodes)])
                    nxt = [(d, a) for d, a in sorted(edge[e]) if prev_d <= d <= d0 + win
                           and (not amount_rule or keep_lo * prev_a <= a <= prev_a * 1.001)]
                    if not nxt:
                        ok = False
                        break
                    prev_d, prev_a = nxt[0]
                    path.append(prev_a)
                if ok:
                    hit = dict(nodes=nodes, start_day=d0, span=prev_d - d0, amounts=path)
                    break
            if hit:
                found.append(hit)
                break
    return found


def baseline_max_counts(tx, accounts):
    """Naive rule input: max number of deposits received in any 7-day window."""
    ext = set(accounts.loc[accounts.label == "external", "account"])
    res = {}
    for a, inc in tx.groupby("dst"):
        if a in ext:
            continue
        days = inc.day.values
        res[a] = max((int(((days >= s) & (days < s + WIN)).sum()) for s in set(days) if s >= WARMUP), default=0)
    return res


def baseline_cycle_members(tx, accounts):
    """Naive cycle rule: any time-ordered loop of 3-4 accounts within 14 days, ignoring amounts."""
    cs = find_cycles(tx, accounts, max_len=4, win=14, min_amount=0, amount_rule=False)
    return {n for c in cs for n in c["nodes"]}
