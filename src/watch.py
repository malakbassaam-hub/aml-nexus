"""Evidence Watch + keep-open record.
Starting a watch is a HUMAN decision. The system only gathers evidence (for AND against) and reports it.
Links to other accounts must be backed by actual transfers with the watched account - relationship alone is never enough.
Durations are policy parameters (US guidance mentions up to 6 months for law-enforcement 'keep open' requests); not legal advice."""
from dataclasses import dataclass, field
from .risk import build_cases

CAPS = {"internal_policy": 90, "law_enforcement_request": 180}
REVIEW_EVERY = 30


@dataclass
class KeepOpen:
    account: str
    basis: str  # internal_policy | law_enforcement_request
    purpose: str
    requested_by: str
    start_day: int
    duration_days: int
    reviews: list = field(default_factory=list)
    extensions: list = field(default_factory=list)

    def __post_init__(self):
        if self.basis not in CAPS:
            raise ValueError("unknown basis")
        if not self.purpose.strip():
            raise ValueError("a purpose is required")
        if not 1 <= self.duration_days <= CAPS[self.basis]:
            raise ValueError(f"duration must be 1-{CAPS[self.basis]} days for {self.basis}")

    @property
    def end_day(self):
        return self.start_day + self.duration_days + sum(e["days"] for e in self.extensions)

    def extend(self, days, reason, approver, day):
        if not reason.strip():
            raise ValueError("an extension needs a written reason")
        if not 1 <= days <= CAPS[self.basis]:
            raise ValueError("extension length out of range")
        if day >= self.end_day:
            raise ValueError("watch already expired; a new watch must be opened")
        self.extensions.append(dict(days=days, reason=reason, approver=approver, day=day))

    def status(self, day):
        if day >= self.end_day:
            return "expired"
        return "review_due" if day - max([self.start_day] + self.reviews) >= REVIEW_EVERY else "active"


class EvidenceWatch:
    def __init__(self, tx, accounts, keep_open, audit):
        self.tx, self.acc, self.ko, self.audit, self.links = tx, accounts, keep_open, audit, {}
        self.ext = set(accounts.loc[accounts.label == "external", "account"])
        audit.add(keep_open.requested_by, "watch_started", keep_open.account,
                  dict(basis=keep_open.basis, purpose=keep_open.purpose, end_day=keep_open.end_day), keep_open.start_day)

    def _guard(self, day):
        if self.ko.status(day) == "expired":
            raise PermissionError("watch expired: no further evidence collection")

    def snapshot(self, day):
        self._guard(day)
        a, t = self.ko.account, self.tx[self.tx.day <= day]
        nb = {a}
        for _ in range(2):  # 2 undirected hops cover loops up to length 5
            hit = t[t.src.isin(nb) | t.dst.isin(nb)]
            nb |= set(hit.src) | set(hit.dst)
        cs = build_cases(t[t.src.isin(nb) & t.dst.isin(nb)], self.acc, now=day)
        row = cs[cs.account == a]
        if row.empty:
            return dict(day=day, suspicion=0.0, counter=0.0, tier="Clear", supporting=[], counter_evidence=[])
        r = row.iloc[0]
        return dict(day=day, suspicion=float(r.suspicion), counter=float(r.counter), tier=r.tier,
                    supporting=list(r.supporting), counter_evidence=list(r.counter_evidence))

    def suggest_links(self, day, lookback=30, min_txs=2):
        """Counterparties with real transfers (>= min_txs) - split into monitorable (in-bank) and outside-bank."""
        a = self.ko.account
        t = self.tx[(self.tx.day <= day) & (self.tx.day > day - lookback) & ((self.tx.src == a) | (self.tx.dst == a))]
        t = t.assign(other=t.src.where(t.src != a, t.dst))
        g = t.groupby("other").amount.agg(["count", "sum"])
        out = []
        for other, r in g[g["count"] >= min_txs].iterrows():
            out.append(dict(account=other, monitorable=other not in self.ext,
                            reason=f"{int(r['count'])} transfers totalling {r['sum']:,.0f} with {a} in the last {lookback} days"))
        return out

    def approve_link(self, other, reviewer, day):
        self._guard(day)
        match = [s for s in self.suggest_links(day) if s["account"] == other and s["monitorable"]]
        if not match:
            raise ValueError("link must be backed by transfers with the watched account and be an in-bank account")
        self.links[other] = match[0]["reason"]
        self.audit.add(reviewer, "link_approved", other, dict(watched=self.ko.account, reason=match[0]["reason"]), day)

    def packet(self, day):
        """What the human reviewer sees before deciding. The decision itself is always the reviewer's."""
        start, now = self.snapshot(self.ko.start_day), self.snapshot(day)
        hint = {"Escalate": "evidence now supports escalation; a human decides on any restriction",
                "Monitor": "evidence is still mixed; consider continuing the watch",
                }.get(now["tier"], "evidence no longer supports suspicion; consider closing the watch (Clear)")
        return dict(account=self.ko.account, status=self.ko.status(day), start=start, now=now,
                    linked={l: self.snapshot_for(l, day)["tier"] for l in self.links}, hint=hint)

    def snapshot_for(self, other, day):
        w = EvidenceWatch.__new__(EvidenceWatch)
        w.__dict__.update(self.__dict__)
        w.ko = KeepOpen(other, self.ko.basis, self.ko.purpose, self.ko.requested_by, self.ko.start_day, self.ko.duration_days)
        return w.snapshot(day)

    def decide(self, reviewer, decision, reason, day, extend_days=0):
        if decision not in ("Clear", "Escalate", "Extend") or not reason.strip():
            raise ValueError("decision must be Clear/Escalate/Extend with a written reason")
        if decision == "Extend":
            self.ko.extend(extend_days, reason, reviewer, day)
        self.audit.add(reviewer, f"decision_{decision.lower()}", self.ko.account, dict(reason=reason), day)
