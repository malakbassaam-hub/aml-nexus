"""Automation-bias guard: measures whether human review is real review or rubber-stamping.
Thresholds are policy parameters, NOT empirically validated limits."""
from dataclasses import dataclass
from statistics import median

MIN_CASES, AGREE_LIMIT, FAST_SECONDS, CE_MIN = 10, 0.95, 20, 0.30


@dataclass
class Review:
    reviewer: str
    case: str
    recommendation: str
    decision: str
    seconds: float
    opened_counter_evidence: bool


def can_submit(recommendation, decision, opened_counter_evidence):
    """Friction: confirming a freeze-level recommendation requires opening the counter-evidence first."""
    if recommendation == "Escalate" and decision == "Escalate" and not opened_counter_evidence:
        return False, "Open the counter-evidence before confirming an escalation."
    return True, ""


def bias_report(reviews, min_cases=MIN_CASES):
    out = {}
    for who in sorted({r.reviewer for r in reviews}):
        rs = [r for r in reviews if r.reviewer == who]
        agree = sum(r.decision == r.recommendation for r in rs) / len(rs)
        ce = sum(r.opened_counter_evidence for r in rs) / len(rs)
        med = median(r.seconds for r in rs)
        flag = len(rs) >= min_cases and agree >= AGREE_LIMIT and (med < FAST_SECONDS or ce < CE_MIN)
        out[who] = dict(cases=len(rs), agreement=round(agree, 3), median_seconds=med,
                        counter_evidence_opened=round(ce, 3), possible_rubber_stamping=flag)
    return out
