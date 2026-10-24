"""Benford's-law check on the first digits of incoming amounts (Newcomb 1881, Benford 1938; used in forensic accounting).
Used ONLY relative to peers: legitimate price points also break Benford, so an absolute 'non-conforming' verdict would be wrong.
Needs at least MIN_N payments; otherwise the answer is 'insufficient data'."""
import math
import numpy as np

EXPECTED = np.array([math.log10(1 + 1 / d) for d in range(1, 10)])
MIN_N = 20


def first_digits(amounts):
    out = []
    for v in amounts:
        v = abs(float(v))
        if v >= 1:
            out.append(int(str(int(v))[0]))
    return np.array(out, dtype=int)


def digit_profile(amounts):
    d = first_digits(amounts)
    if len(d) < MIN_N:
        return None
    obs = np.array([(d == k).mean() for k in range(1, 10)])
    return dict(n=len(d), observed=obs, expected=EXPECTED, mad=float(np.abs(obs - EXPECTED).mean()))


def peer_table(tx, acc, day):
    """MAD of every receiving account with enough payments up to `day`, plus its percentile among those peers."""
    ext = set(acc.loc[acc.label == "external", "account"])
    t = tx[tx.day <= day]
    mads = {}
    for a, g in t.groupby("dst"):
        if a in ext:
            continue
        p = digit_profile(g.amount.to_numpy())
        if p:
            mads[a] = p["mad"]
    if not mads:
        return {}
    vals = np.array(sorted(mads.values()))
    return {a: dict(mad=m, pct=float((vals <= m).mean())) for a, m in mads.items()}


def to_svg(p, w=460, h=230):
    """Observed first-digit shares (red bars) against Benford's expectation (blue markers)."""
    obs, exp = p["observed"], p["expected"]
    top, base, left = 40, h - 38, 44
    mx = max(obs.max(), exp.max()) * 1.15
    sc = (base - top) / mx
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;display:block;margin:0 auto">',
             f'<rect width="{w}" height="{h}" rx="12" fill="#FFFFFF" stroke="#D5DEEB"/>',
             f'<text x="{w / 2}" y="22" text-anchor="middle" font-size="13" font-weight="600" font-family="Inter,Arial,sans-serif" fill="#0B1F3A">'
             f'First digit of {p["n"]} incoming payments (deviation {p["mad"]:.3f})</text>',
             f'<line x1="{left - 4}" y1="{base}" x2="{w - 10}" y2="{base}" stroke="#9AA8BD"/>']
    for i in range(9):
        x = left + i * 45
        parts.append(f'<rect x="{x}" y="{base - obs[i] * sc:.1f}" width="30" height="{obs[i] * sc:.1f}" rx="3" fill="#D93025" opacity=".85"/>')
        parts.append(f'<circle cx="{x + 15}" cy="{base - exp[i] * sc:.1f}" r="5" fill="#0070E0" stroke="#fff" stroke-width="1.5"/>')
        parts.append(f'<text x="{x + 15}" y="{base + 16}" text-anchor="middle" font-size="12" font-family="Inter,Arial,sans-serif" fill="#0B1F3A">{i + 1}</text>')
    parts.append(f'<text x="{left}" y="{h - 8}" font-size="11" font-family="Inter,Arial,sans-serif" fill="#5A6B85">red bars = what we see · blue dots = what Benford predicts</text></svg>')
    return "".join(parts)
