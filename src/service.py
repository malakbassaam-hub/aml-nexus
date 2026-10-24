"""Logic behind the dashboard. No Streamlit imports here, so it is unit-tested."""
from pathlib import Path

import pandas as pd
from . import ledger as ledger_mod
from .audit import AuditLog
from .benford import digit_profile, peer_table
from .data_gen import generate
from .review import Review, bias_report, can_submit
from .risk import build_cases
from .watch import EvidenceWatch, KeepOpen

LEDGER_PATH = Path(__file__).resolve().parent.parent / "docs" / "ledger_model.json"
TIER_COLORS = {"Clear": "#1E8E3E", "Verify": "#F2A900", "Monitor": "#0070E0", "Escalate": "#D93025"}
TIER_ORDER = {"Escalate": 0, "Monitor": 1, "Verify": 2, "Clear": 3}

# Demo scenarios: (account, anchor, offset). Anchor "in" = first inflow day, "any" = first transaction day, int = fixed day.
SCENARIOS = {
    "1 - Ring forming": dict(account="COL0", anchor="in", offset=2,
        note="Many new accounts pay one collector just under the threshold. Watch the evidence grow."),
    "2 - Slow drip": dict(account="DRIP0", anchor="in", offset=14,
        note="Dispersed payments into a young account over weeks: hard to see in any single week."),
    "3 - Legit shop": dict(account="SHOP0", anchor=40, offset=0,
        note="A busy shop that looks suspicious at first glance. The counter-evidence matters here."),
    "4 - Emergency fundraiser": dict(account="FUND0", anchor="in", offset=4,
        note="A genuine campaign that pays out fast. The system cannot know it is genuine: a human must verify."),
    "5 - Closed loop": dict(account="LC0_0", anchor="any", offset=3,
        note="Funds travel through several accounts and return to the start, losing a small cut each hop."),
}


class Workbench:
    def __init__(self, seed=7):
        self.acc, self.tx = generate(seed)
        self.role = self.acc.set_index("account")["role"].to_dict()
        self.last_day = int(self.tx.day.max())
        self.now, self.selected, self.scenario_note = 40, None, "Pick a demo scenario in the sidebar."
        self.audit, self.watches, self.closed, self.reviews, self.decisions = AuditLog(), {}, {}, [], {}
        self._cases, self._snap, self._peers = {}, {}, {}
        try:
            self.ledger = ledger_mod.load(LEDGER_PATH)[:2]
        except (OSError, ValueError, KeyError):
            self.ledger = None  # the ledger panel is simply hidden if the trained model file is missing

    # ---- queue and cases -------------------------------------------------
    def cases_at(self, day):
        if day not in self._cases:
            self._cases[day] = build_cases(self.tx[self.tx.day <= day], self.acc, now=day)
        return self._cases[day]

    def queue(self, reveal=False):
        q = self.cases_at(self.now)
        q = q[q.tier != "Clear"].copy()
        q["order"] = q.tier.map(TIER_ORDER)
        q = q.sort_values(["order", "suspicion"], ascending=[True, False]).drop(columns="order")
        if reveal:
            q["synthetic_truth"] = q.account.map(self.role)
        return q.reset_index(drop=True)

    def case(self, account):
        c = self.cases_at(self.now)
        r = c[c.account == account]
        return None if r.empty else r.iloc[0]

    def advance(self, days=7):
        self.now = min(self.last_day, self.now + days)

    def load_scenario(self, name):
        sc = SCENARIOS[name]
        a, t = sc["account"], self.tx
        base = sc["anchor"] if isinstance(sc["anchor"], int) else int(
            (t[t.dst == a] if sc["anchor"] == "in" else t[(t.src == a) | (t.dst == a)]).day.min())
        self.now, self.selected, self.scenario_note = min(self.last_day, base + sc["offset"]), a, sc["note"]
        return a

    # ---- decisions -------------------------------------------------------
    def _review(self, reviewer, account, rec, decision, seconds, ce):
        self.reviews.append(Review(reviewer, account, rec, decision, float(seconds), bool(ce)))

    def decide_case(self, reviewer, account, decision, reason, seconds, opened_counter_evidence):
        row = self.case(account)
        rec = "Clear" if row is None else row.tier
        if not reason.strip():
            return False, "A written reason is required."
        ok, msg = can_submit(rec, decision, opened_counter_evidence)
        if not ok:
            return False, msg
        self._review(reviewer, account, rec, decision, seconds, opened_counter_evidence)
        self.decisions[account] = decision
        self.audit.add(reviewer, "case_decision", account, dict(recommended=rec, decision=decision, reason=reason), self.now)
        return True, f"Decision recorded: {decision}."

    # ---- Evidence Watch --------------------------------------------------
    def start_watch(self, account, basis, purpose, requested_by, duration, seconds=None, opened_counter_evidence=False):
        old = self.watches.get(account)
        if old and account not in self.closed and old.ko.status(self.now) != "expired":
            raise ValueError("This account already has an active watch.")
        ko = KeepOpen(account, basis, purpose, requested_by, self.now, int(duration))
        w = EvidenceWatch(self.tx, self.acc, ko, self.audit)
        self.watches[account] = w
        self.closed.pop(account, None)
        if seconds is not None:
            row = self.case(account)
            self._review(requested_by, account, "Clear" if row is None else row.tier, "Monitor", seconds, opened_counter_evidence)
        return w

    def watch_status(self, account):
        if account in self.closed:
            return f"closed ({self.closed[account]})"
        return self.watches[account].ko.status(self.now)

    def _snapshot(self, account, day):
        k = (account, day)
        if k not in self._snap:
            self._snap[k] = self.watches[account].snapshot(day)
        return self._snap[k]

    def trajectory(self, account, step=3):
        w = self.watches[account]
        end = min(self.now, w.ko.end_day - 1)
        days = list(range(w.ko.start_day, end + 1, step))
        if not days or days[-1] != end:
            days.append(end)
        rows = []
        for d in days:
            s = self._snapshot(account, d)
            rows.append(dict(day=d, suspicion=s["suspicion"], counter=s["counter"], tier=s["tier"]))
        return pd.DataFrame(rows)

    def packet(self, account):
        w = self.watches[account]
        day = min(self.now, w.ko.end_day - 1)
        p = w.packet(day)
        p["status"], p["expired"] = self.watch_status(account), w.ko.status(self.now) == "expired"
        return p

    def link_suggestions(self, account):
        w = self.watches[account]
        return w.suggest_links(min(self.now, w.ko.end_day - 1))

    def approve_link(self, account, other, reviewer):
        self.watches[account].approve_link(other, reviewer, self.now)

    def decide_watch(self, account, reviewer, decision, reason, extend_days=0):
        w = self.watches[account]
        w.decide(reviewer, decision, reason, self.now, extend_days)
        if decision in ("Clear", "Escalate"):
            self.closed[account] = decision
            self.decisions[account] = decision
        w.ko.reviews.append(self.now)

    # ---- reviewer quality -----------------------------------------------
    def simulate_reviewers(self, kind):
        """Adds clearly-labelled SIMULATED reviews so the guard can be demonstrated."""
        recs = ["Escalate", "Monitor", "Verify", "Escalate"] * 3
        if kind == "fast":
            for i, r in enumerate(recs):
                self._review("reviewer_B (simulated)", f"sim{i}", r, r, 5 + i % 4, False)
        else:
            for i, r in enumerate(recs):
                self._review("reviewer_A (simulated)", f"sim{i}", r, r if i % 4 else "Verify", 80 + 5 * i, True)
        self.audit.add("system", "simulated_reviews_added", kind, dict(count=len(recs)), self.now)

    def quality(self):
        return bias_report(self.reviews)

    # ---- statistical second opinion -----------------------------------------
    def inflow_profile(self, account):
        t = self.tx[(self.tx.dst == account) & (self.tx.day <= self.now)]
        return digit_profile(t.amount.to_numpy())

    def ledger_view(self, account, row):
        """Evidence ledger for a case, or None when it does not apply (closed loops) or no model file is available."""
        if self.ledger is None or row.kind not in ("fan_in", "slow_accumulation") or not row.features:
            return None
        if self.now not in self._peers:
            self._peers[self.now] = peer_table(self.tx, self.acc, self.now)
        pct = self._peers[self.now].get(account, {}).get("pct")
        model, threshold = self.ledger
        net, entries = ledger_mod.score(model, ledger_mod.bin_features(row.features, row.kind, pct))
        rules_flag, model_flag = row.tier in ("Monitor", "Escalate"), net >= threshold
        verdict = {(True, True): "Both the rules and the learned model flag this account.",
                   (True, False): "The rules flag this account but the learned model does not: read the counter-evidence closely.",
                   (False, True): "The learned model flags this account but the rules do not: worth a second look.",
                   (False, False): "Neither the rules nor the learned model flag it as a strong case."}[(rules_flag, model_flag)]
        return dict(net=net, threshold=threshold, model_flag=model_flag, verdict=verdict,
                    entries=[(ledger_mod.TITLES[f], b, d) for f, b, d in entries])
