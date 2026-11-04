"""Printable case report: one self-contained HTML file (open it and use the browser's Print > Save as PDF).
It carries a SHA-256 fingerprint of its body so later edits can be detected. The fingerprint does not prove who wrote it.
Synthetic data only; a recommendation, never a decision."""
import hashlib
import html
import re
from datetime import datetime, timezone

from .benford import to_svg as benford_svg
from .evalview import KNOWN_LIMITS
from .flowmap import build_geometry, to_svg as flow_svg
from .risk import PARAMS
from .why import breakdown, decision_path, what_would_change

CSS = ("body{font-family:Inter,'Segoe UI',Arial,sans-serif;color:#0B1F3A;max-width:900px;margin:24px auto;padding:0 16px;line-height:1.45}"
       "h1{color:#003087;margin-bottom:0}h2{border-bottom:2px solid #0070E0;padding-bottom:4px;margin-top:28px}"
       ".banner{background:#FFF4D6;border:1px solid #F2A900;padding:8px 12px;border-radius:8px}"
       ".badge{display:inline-block;padding:2px 12px;border-radius:12px;color:#fff;font-weight:700}"
       ".two{display:flex;gap:24px}.two>div{flex:1}table{border-collapse:collapse;width:100%}td,th{border:1px solid #D5DEEB;padding:4px 8px;text-align:left;font-size:.9rem}"
       "td.n{text-align:right}.small{font-size:.85rem;color:#5A6B85}.fp{font-family:monospace;word-break:break-all}"
       "@media print{body{margin:0}h2{page-break-after:avoid}svg{max-width:100%}}")
COLORS = {"Clear": "#1E8E3E", "Verify": "#F2A900", "Monitor": "#0070E0", "Escalate": "#D93025"}
LIMITS = KNOWN_LIMITS + ["This report is a recommendation and an audit record. It is not a decision, an accusation or legal advice."]


def _e(x):
    return html.escape(str(x))


def _ul(items, empty):
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else f"<p><i>{_e(empty)}</i></p>"


def _rows(items):
    return "".join(f"<tr><td>{_e(l)}</td><td class='n'>{v:+.2f}</td></tr>" for l, v in items) or "<tr><td colspan='2'><i>None</i></td></tr>"


def case_report_html(wb, account, hub_color="#003087"):
    row = wb.case(account)
    if row is None:
        raise ValueError("no open case for this account on this day")
    bd, (tier, why) = breakdown(row), decision_path(float(row.suspicion), float(row.counter))
    lv, bp = wb.ledger_view(account, row), wb.inflow_profile(account)
    geo = build_geometry(wb.tx, wb.acc, account, wb.now, as_cycle=(row.kind == "cycle"))
    audit = [e for e in wb.audit.entries if e["subject"] == account or (e.get("detail") or {}).get("watched") == account]
    b = [f"<h1>AML-Nexus case report</h1><p class='small'>Case {_e(account)} · simulated day {wb.now} · generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</p>",
         "<p class='banner'><b>Synthetic data. A recommendation, not a decision.</b> A human reviewer decides.</p>",
         f"<h2>Summary</h2><p>System recommendation: <span class='badge' style='background:{COLORS.get(row.tier, '#555')}'>{_e(row.tier)}</span> "
         f"· suspicion {row.suspicion:.2f} · counter-evidence {row.counter:.2f}</p>",
         f"<h2>Evidence</h2><div class='two'><div><h3>For suspicion</h3>{_ul(row.supporting, 'None')}</div>"
         f"<div><h3>Against suspicion</h3>{_ul(row.counter_evidence, 'No counter-evidence found.')}</div></div>",
         f"<h2>How the score was built</h2><div class='two'><div><table><tr><th>For (total {bd['total_for']:.2f})</th><th></th></tr>{_rows(bd['for_items'])}</table></div>"
         f"<div><table><tr><th>Against (total {bd['total_against']:.2f})</th><th></th></tr>{_rows(bd['against_items'])}</table></div></div>"
         + "".join(f"<p class='small'>Note: {_e(n)}</p>" for n in bd["notes"])
         + f"<p><b>Decision path:</b> {_e(why)} → <b>{_e(tier)}</b></p>"
         + _ul(what_would_change(float(row.suspicion), float(row.counter)), "No nearby threshold changes the recommendation."),
         f"<h2>Money-flow map (as of day {wb.now})</h2>{flow_svg(geo, hub_color)}"]
    if lv is None:
        b.append("<h2>Statistical second opinion</h2><p><i>Not applicable to this pattern (or no trained model is available).</i></p>")
    else:
        b.append(f"<h2>Statistical second opinion (evidence ledger)</h2><table><tr><th>Evidence</th><th>Decibans</th></tr>"
                 + "".join(f"<tr><td>{_e(t)}: {_e(v)}</td><td class='n'>{d:+.1f}</td></tr>" for t, v, d in lv["entries"])
                 + f"</table><p>Net {lv['net']:+.1f} dB (model flags at {lv['threshold']:+.1f} dB or more). {_e(lv['verdict'])}</p>"
                 "<p class='small'>Same features as the rules, weights learned from synthetic data: a second opinion, not independent evidence.</p>")
    if bp is not None:
        b.append(f"<h2>First-digit (Benford) check</h2>{benford_svg(bp)}<p class='small'>Judged against peers only: honest price points also break Benford's law.</p>")
    w = wb.watches.get(account)
    if w:
        traj = wb.trajectory(account)
        b.append(f"<h2>Evidence Watch</h2><p>Status: {_e(wb.watch_status(account))} · basis {_e(w.ko.basis)} · purpose: {_e(w.ko.purpose)} · "
                 f"day {w.ko.start_day} to {w.ko.end_day}. No restriction is placed on the account by a watch.</p><table><tr><th>Day</th><th>Recommendation</th><th>Suspicion</th><th>Counter-evidence</th></tr>"
                 + "".join(f"<tr><td>{r.day}</td><td>{_e(r.tier)}</td><td class='n'>{r.suspicion:.2f}</td><td class='n'>{r.counter:.2f}</td></tr>" for r in traj.itertuples())
                 + "</table>" + (_ul([f"{k}: {v}" for k, v in w.links.items()], "") if w.links else ""))
    b.append("<h2>Human actions and audit trail</h2>" + ("<table><tr><th>#</th><th>Day</th><th>Who</th><th>Action</th><th>Detail</th></tr>"
             + "".join(f"<tr><td>{e['seq']}</td><td>{_e(e['day'])}</td><td>{_e(e['actor'])}</td><td>{_e(e['action'])}</td><td>{_e('; '.join(f'{k}: {v}' for k, v in (e['detail'] or {}).items()))}</td></tr>" for e in audit)
             + f"</table><p class='small'>Audit hash chain: {'valid' if wb.audit.verify() else 'BROKEN'}.</p>" if audit else "<p><i>No human actions recorded for this case yet.</i></p>"))
    led = f"statistical model cut {wb.ledger[1]:+.1f} dB" if wb.ledger else "no statistical model loaded"
    b.append(f"<h2>Versions and policy</h2><p class='small'>Rules: counter-evidence cut-off for Monitor {PARAMS['c_mon']}; {led}. Flow-map window 30 days.</p>"
             "<h2>Known limits</h2>" + _ul(LIMITS, ""))
    body = "\n".join(b)
    fp = hashlib.sha256(body.encode()).hexdigest()
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>AML-Nexus case {_e(account)}</title><style>{CSS}</style></head><body>"
            f"<!--BODY-->{body}<!--/BODY--><hr><p class='small'>Report fingerprint (SHA-256 of the report body): <span class='fp'>{fp}</span></p></body></html>")


def verify_fingerprint(text):
    m = re.search(r"<!--BODY-->(.*)<!--/BODY-->.*?class='fp'>([0-9a-f]{64})<", text, re.S)
    return bool(m) and hashlib.sha256(m.group(1).encode()).hexdigest() == m.group(2)
