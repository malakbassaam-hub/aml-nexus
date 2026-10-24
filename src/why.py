"""Transparent reasoning: exact score breakdown, the decision path, and what would flip the recommendation."""
from .risk import PARAMS, recommend

LABELS = {
    "breadth": "Many distinct senders", "new_accounts": "Senders are newly opened accounts",
    "structuring": "Deposits sit just under the reporting threshold", "pass_through": "Money moved out quickly",
    "typology": "Base weight: new-account accumulation pattern", "volume": "Large cumulative volume",
    "large_payments": "Large individual payments", "cap": "Cap: indirect evidence alone cannot escalate",
    "closed_loop": "Closed loop with a small cut at each hop",
    "repeat": "Senders are established counterparties", "established": "Senders are long-standing accounts",
    "retention": "Funds retained (neutral while not yet observable)",
}


def breakdown(row):
    """Rows of (label, value) for and against; the values add up exactly to the two scores."""
    f = [(LABELS.get(k, k), v) for k, v in row.components.items() if v]
    a = [(LABELS.get(k, k), v) for k, v in row.counter_components.items() if v]
    return dict(for_items=f, against_items=a, total_for=round(sum(v for _, v in f), 3),
                total_against=round(sum(v for _, v in a), 3), notes=list(row.notes))


def decision_path(s, c, c_mon=None):
    c_mon = PARAMS["c_mon"] if c_mon is None else c_mon
    tier = recommend(s, c, c_mon)
    if s >= 0.75 and c < 0.4:
        why = f"Suspicion {s:.2f} is at least 0.75 and counter-evidence {c:.2f} is below 0.40."
    elif s >= 0.75:
        why = f"Suspicion {s:.2f} is at least 0.75, but counter-evidence {c:.2f} is 0.40 or more, so the system asks for more evidence instead of escalating."
    elif s >= 0.5 and c < c_mon:
        why = f"Suspicion {s:.2f} is at least 0.50 and counter-evidence {c:.2f} is below {c_mon:.2f}."
    elif s >= 0.5:
        why = f"Suspicion {s:.2f} is at least 0.50, but counter-evidence {c:.2f} is {c_mon:.2f} or more: contact the customer rather than watch."
    elif s >= 0.35:
        why = f"Suspicion {s:.2f} is between 0.35 and 0.50" + (f" and counter-evidence {c:.2f} is 0.60 or more." if c >= 0.6 else ".")
    else:
        why = f"Suspicion {s:.2f} is below 0.35."
    return tier, why


def what_would_change(s, c, c_mon=None):
    """Smallest move (in steps of 0.01) of either score that changes the recommendation."""
    base, out = recommend(s, c, c_mon), []
    for name, fn in (("counter-evidence rose", lambda d: (s, c + d)), ("counter-evidence fell", lambda d: (s, c - d)),
                     ("suspicion rose", lambda d: (s + d, c)), ("suspicion fell", lambda d: (s - d, c))):
        for i in range(1, 101):
            d = i / 100
            s2, c2 = fn(d)
            if not (0 <= s2 <= 1.0001 and 0 <= c2 <= 1.0001):
                break
            t = recommend(s2, c2, c_mon)
            if t != base:
                out.append(f"If {name} by {d:.2f}, the recommendation would become {t}.")
                break
    return out
