"""Money-flow map: a self-contained animated SVG (no libraries, no CDN). Inspired by John Snow's 1854 cholera map:
the picture shows what a table of numbers hides. Left: who paid in. Centre: the account. Right: where money left."""
import html
import numpy as np
from .detectors import find_cycles

W, H = 900, 540
FRAME = 580  # iframe height used by the dashboard
NEW, OLD, OUTSIDE = "#D93025", "#1E8E3E", "#5A6B85"


def _k(v):
    return f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"


def _ys(n, lo, hi):
    return [(lo + hi) / 2] if n == 1 else list(np.linspace(lo, hi, n))


def build_geometry(tx, acc, account, day, window=30, max_senders=14, max_out=6, as_cycle=False):
    opened = acc.set_index("account")["opened_day"].to_dict()
    ext = set(acc.loc[acc.label == "external", "account"])
    t = tx[(tx.day <= day) & (tx.day > day - window)]
    if as_cycle:
        for c in find_cycles(t, acc):
            if account in c["nodes"]:
                n = len(c["nodes"])
                ang = [-np.pi / 2 + 2 * np.pi * i / n for i in range(n)]
                nodes = [dict(id=v, x=450 + 190 * np.cos(a), y=270 + 170 * np.sin(a), hub=v == account) for v, a in zip(c["nodes"], ang)]
                edges = [dict(a=i, b=(i + 1) % n, amount=c["amounts"][i]) for i in range(n)]
                return dict(kind="cycle", nodes=nodes, edges=edges, day=day,
                            stats=f"Closed loop of {n} accounts; first hop {_k(c['amounts'][0])}, funds return to the start " + ("on the same day" if c["span"] == 0 else f"within {c['span']} days"))
    inc, out = t[t.dst == account], t[t.src == account]
    g = inc.groupby("src").agg(amount=("amount", "sum"), first=("day", "min"), last=("day", "max")).reset_index()
    born = np.array([opened.get(a, -1000) for a in g.src], dtype=float)  # plain numpy: immune to pandas/pyarrow dtype differences
    g["new"] = (g["first"].to_numpy(dtype=float) - born) < 30
    g = g.sort_values(["first", "amount"], ascending=[True, False])
    shown, rest = g.head(max_senders), g.iloc[max_senders:]
    senders = [dict(id=r.src, amount=r.amount, new=bool(r.new), recent=int(r.last) >= day - 2) for r in shown.itertuples()]
    if len(rest):
        senders.append(dict(id=f"+{len(rest)} others", amount=float(rest.amount.sum()), new=bool(rest.new.mean() > 0.5), recent=False, more=True))
    for s_, y in zip(senders, _ys(len(senders), 60, H - 70)):
        s_["y"] = y
    o = out.groupby("dst").agg(amount=("amount", "sum"), last=("day", "max")).reset_index().sort_values("amount", ascending=False).head(max_out)
    outs = [dict(id=r.dst, amount=r.amount, outside=r.dst in ext, recent=int(r.last) >= day - 2) for r in o.itertuples()]
    for o_, y in zip(outs, _ys(len(outs), 110, H - 120)):
        o_["y"] = y
    stats = (f"Last {window} days: {_k(inc.amount.sum())} in from {inc.src.nunique()} accounts"
             f" · {_k(out.amount.sum())} out to {out.dst.nunique()} destination(s)")
    return dict(kind="funnel", hub=account, senders=senders, outs=outs, day=day, stats=stats)


def _bez(x1, y1, x2, y2):
    return f"M{x1:.0f},{y1:.0f} C{x1 + 150:.0f},{y1:.0f} {x2 - 150:.0f},{y2:.0f} {x2:.0f},{y2:.0f}"


def _width(a):
    return float(np.clip(1.2 + np.sqrt(max(a, 0)) / 22, 1.2, 8))


def to_svg(geo, hub_color="#003087"):
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMin meet" style="width:100%;max-height:{FRAME - 20}px;height:auto;display:block;margin:0 auto">',
         "<style>.flow{stroke-dasharray:0.1 18;stroke-linecap:round;animation:dash 1.1s linear infinite;fill:none}.base{fill:none;opacity:.22}"
         "@keyframes dash{to{stroke-dashoffset:-36}}text{font-family:Inter,'Segoe UI',Arial,sans-serif;fill:#0B1F3A}"
         ".pulse{animation:pulse 1.8s ease-in-out infinite}@keyframes pulse{50%{opacity:.55}}</style>",
         '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF1FB"/></linearGradient>'
         '<filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
         f'<rect width="{W}" height="{H}" rx="14" fill="url(#bg)" stroke="#D5DEEB"/>']
    if geo["kind"] == "cycle":
        n = geo["nodes"]
        for e in geo["edges"]:
            a, b = n[e["a"]], n[e["b"]]
            mx, my = (a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2
            ln = f'x1="{a["x"]:.0f}" y1="{a["y"]:.0f}" x2="{b["x"]:.0f}" y2="{b["y"]:.0f}" stroke="{NEW}"'
            p.append(f'<line class="base" {ln} stroke-width="{_width(e["amount"]):.1f}"/><line class="flow" {ln} stroke-width="{_width(e["amount"]) * .9:.1f}" opacity=".95"/>')
            p.append(f'<text x="{mx:.0f}" y="{my:.0f}" font-size="13" text-anchor="middle" font-weight="600" stroke="#fff" stroke-width="4" paint-order="stroke">{_k(e["amount"])}</text>')
        for v in n:
            p.append(f'<circle cx="{v["x"]:.0f}" cy="{v["y"]:.0f}" r="{30 if v["hub"] else 22}" fill="{hub_color if v["hub"] else "#FFFFFF"}" stroke="{hub_color}" stroke-width="3"/>')
            p.append(f'<text x="{v["x"]:.0f}" y="{v["y"] + 4:.0f}" font-size="11" text-anchor="middle" font-weight="700" fill="{"#fff" if v["hub"] else "#0B1F3A"}" style="fill:{"#fff" if v["hub"] else "#0B1F3A"}">{html.escape(v["id"])}</text>')
    else:
        hx, hy, sx, ox = 450, H / 2, 205, 720
        for s_ in geo["senders"]:
            c = NEW if s_["new"] else OLD
            d_ = _bez(sx + 14, s_["y"], hx - 36, hy)
            p.append(f'<path class="base" d="{d_}" stroke="{c}" stroke-width="{_width(s_["amount"]):.1f}"/>')
            p.append(f'<path class="flow{" pulse" if s_["recent"] else ""}" d="{d_}" stroke="{c}" stroke-width="{_width(s_["amount"]) * .9:.1f}" opacity="{.98 if s_["recent"] else .7}"{" filter=\'url(#glow)\'" if s_["recent"] else ""}/>')
            p.append(f'<circle cx="{sx}" cy="{s_["y"]:.0f}" r="{10 if not s_.get("more") else 14}" fill="{c}"/>')
            p.append(f'<text x="{sx - 18}" y="{s_["y"] + 4:.0f}" font-size="12" text-anchor="end">{html.escape(s_["id"])} · {_k(s_["amount"])}</text>')
        for o_ in geo["outs"]:
            d_ = _bez(hx + 36, hy, ox - 14, o_["y"])
            p.append(f'<path class="base" d="{d_}" stroke="{OUTSIDE}" stroke-width="{_width(o_["amount"]):.1f}"/>')
            p.append(f'<path class="flow" d="{d_}" stroke="{OUTSIDE}" stroke-width="{_width(o_["amount"]) * .9:.1f}" opacity=".85"/>')
            p.append(f'<rect x="{ox - 14}" y="{o_["y"] - 12:.0f}" width="24" height="24" rx="5" fill="{OUTSIDE}"/>')
            p.append(f'<text x="{ox + 20}" y="{o_["y"] - 1:.0f}" font-size="12">{html.escape(o_["id"])} · {_k(o_["amount"])}</text>')
            if o_["outside"]:
                p.append(f'<text x="{ox + 20}" y="{o_["y"] + 14:.0f}" font-size="11" style="fill:#5A6B85">outside bank</text>')
        p.append(f'<circle cx="{hx}" cy="{hy}" r="36" fill="{hub_color}" stroke="#fff" stroke-width="4" filter="url(#glow)"/>')
        p.append(f'<text x="{hx}" y="{hy + 4}" font-size="12" text-anchor="middle" font-weight="700" style="fill:#fff">{html.escape(geo["hub"])}</text>')
        if not geo["senders"]:
            p.append(f'<text x="{hx}" y="{hy + 70}" font-size="14" text-anchor="middle">No inflow in this period</text>')
    p.append(f'<text x="{W / 2}" y="{H - 40}" font-size="14" text-anchor="middle" font-weight="600">{html.escape(geo["stats"])} · day {geo["day"]}</text>')
    lg = [(NEW, "Newly opened sender (&lt;30 days)"), (OLD, "Established sender"), (OUTSIDE, "Destination"), ("#fff", "Bright = payment in last 3 days")]
    x = 40
    for col, label in lg:
        p.append(f'<circle cx="{x}" cy="{H - 16}" r="6" fill="{col}" stroke="#9AA8BD"/><text x="{x + 12}" y="{H - 12}" font-size="12">{label}</text>')
        x += 215
    p.append("</svg>")
    return "".join(p)


def wrap_html(svg):
    """Page for the dashboard's iframe: no margins, and (when the browser allows it) the frame shrinks to the drawing."""
    return ("<style>html,body{margin:0;padding:0;background:transparent}</style>" + svg +
            "<script>function fit(){try{var h=document.querySelector('svg').getBoundingClientRect().height;"
            "window.frameElement.style.height=(h+4)+'px';}catch(e){}}window.addEventListener('load',fit);"
            "window.addEventListener('resize',fit);</script>")
