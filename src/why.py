# src/why.py

LABELS = {
    "amount_anomaly": "Unusual transaction amount",
    "velocity": "High transaction velocity",
    "new_sender": "Recently opened sender account",
    "ring_pattern": "Circular transaction pattern detected",
    "frequent": "Frequent transactions",
    "repeat": "Senders are established counterparties",
    "established": "Senders are long-established",
    "retention": "Funds retained (neutral while not yet observable)"
}

def breakdown(row):
    """Rows of (label, value) for and against; the values add up exactly to the two scores."""
    components = row.get('components', {}) if hasattr(row, 'get') else getattr(row, 'components', {})
    if hasattr(components, 'items'):
        f = [(LABELS.get(k, k), v) for k, v in components.items() if v]
    else:
        f = []
        
    counter_comps = row.get('counter_components', {}) if hasattr(row, 'get') else getattr(row, 'counter_components', {})
    if hasattr(counter_comps, 'items'):
        a = [(LABELS.get(k, k), v) for k, v in counter_comps.items() if v]
    else:
        a = []
        
    notes = row.get('notes', []) if hasattr(row, 'get') else getattr(row, 'notes', [])
    
    return dict(
        for_items=f, 
        against_items=a, 
        total_for=round(sum(v for _, v in f), 3),
        total_against=round(sum(v for _, v in a), 3), 
        notes=list(notes)
    )

def decision_path(s, c, c_mon=None):
    from src.risk import PARAMS, recommend
    c_mon = PARAMS["c_mon"] if c_mon is None else c_mon
    tier = recommend(s, c, c_mon)
    
    if s >= 0.75 and c < 0.4:
        why = f"Suspicion {s:.2f} is at least 0.75 and counter-evidence {c:.2f} is below 0.40."
    elif s >= 0.75:
        why = f"Suspicion {s:.2f} is at least 0.75, but counter-evidence {c:.2f} is 0.40 or higher."
    elif s >= 0.5 and c < c_mon:
        why = f"Suspicion {s:.2f} is at least 0.50 and counter-evidence {c:.2f} is below {c_mon}."
    elif s >= 0.5:
        why = f"Suspicion {s:.2f} is at least 0.50, but counter-evidence {c:.2f} is high."
    else:
        why = f"Suspicion {s:.2f} is below the review threshold."
        
    return tier, why
