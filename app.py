"""AML-Nexus dashboard.  Run:  streamlit run app.py
All data is synthetic. The system recommends; a human decides."""
import json
import time
from datetime import timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.paypal_client import (SAMPLE_RESPONSE, PayPalConfig, analyze, default_origin, fetch_last_days, get_token,
                               to_edges)
from src.explain import AIConfig, facts_from_case, facts_from_packet, summarize
from src.flowmap import FRAME, build_geometry, to_svg, wrap_html
from src.service import SCENARIOS, TIER_COLORS, Workbench
from src.why import breakdown, decision_path, what_would_change
from src.watch import CAPS

st.set_page_config(page_title="AML-Nexus", page_icon="🛡️", layout="wide")
st.markdown(
    """
<style>
.hero{background:linear-gradient(90deg,#003087,#0070E0);color:#fff;padding:18px 24px;border-radius:12px;margin-bottom:10px}
.hero h1{color:#fff;margin:0;font-size:2rem} .hero p{margin:2px 0 0 0;color:#DCEBFF}
.badge{display:inline-block;padding:2px 12px;border-radius:12px;color:#fff;font-weight:600;font-size:.9rem}
.st-key-btn_watch button{background:#0070E0;color:#fff;border:2px solid #003087;font-weight:700;font-size:1.05rem;padding:.7rem 0}
.st-key-btn_clear button{border:2px solid #1E8E3E} .st-key-btn_verify button{border:2px solid #F2A900}
.st-key-btn_escalate button{border:2px solid #D93025}
</style>
<div class="hero"><h1>AML-Nexus</h1><p>Catch the criminals. Protect everyone else.</p></div>
""",
    unsafe_allow_html=True,
)
st.info("Synthetic data, no real customers. The system recommends; a human decides.")

if "wb" not in st.session_state:
    with st.spinner("Generating synthetic bank data..."):
        st.session_state["wb"] = Workbench(7)
        st.session_state["opened_at"] = {}
st.session_state.setdefault("summaries", {})
wb = st.session_state["wb"]
try:
    _k = dict(st.secrets["anthropic"])
    ai_cfg = AIConfig(_k["api_key"], _k.get("model", "claude-haiku-5-5"))
except Exception:
    ai_cfg = None  # no key: a fixed template summary is shown and labelled as such


def flow_map(account, kind, day, tier):
    geo = build_geometry(wb.tx, wb.acc, account, day, as_cycle=(kind == "cycle"))
    components.html(wrap_html(to_svg(geo, TIER_COLORS.get(tier, "#003087"))), height=FRAME)


def bars(items, color, total):
    rows = "".join(
        f"<div style='display:flex;align-items:center;margin:3px 0'><div style='width:46%;font-size:.88rem'>{lab}</div>"
        f"<div style='flex:1;background:#E6ECF5;border-radius:6px;height:14px'><div style='width:{min(100, abs(v) / max(total, 0.01) * 100):.0f}%;"
        f"background:{color};height:14px;border-radius:6px'></div></div><div style='width:54px;text-align:right;font-weight:600'>{v:+.2f}</div></div>"
        for lab, v in items) or "<i>Nothing recorded.</i>"
    return rows


def show_summary(key, facts):
    res = st.session_state["summaries"].get(key)
    if st.button("Generate summary", key=f"sum_{key}"):
        res = st.session_state["summaries"][key] = summarize(facts, ai_cfg)
    if res:
        st.markdown(res["text"])
        st.caption(("🧠 Written by Claude. " if res["source"] == "claude" else "📄 Fixed template, not AI. ") + res["note"])
        with st.expander("Exactly what the model is allowed to see"):
            st.json(res["facts"])


def badge(tier):
    return f"<span class='badge' style='background:{TIER_COLORS.get(tier, '#555')}'>{tier}</span>"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    reviewer = st.text_input("Reviewer ID", "reviewer_1")
    st.markdown("### Demo mode")
    for name in SCENARIOS:
        if st.button(name, key=f"sc_{name}", use_container_width=True):
            st.session_state["case_select"] = wb.load_scenario(name)
            st.rerun()
    st.caption(wb.scenario_note)
    st.divider()
    st.markdown(f"**Simulated day:** {wb.now} / {wb.last_day}")
    if st.button("Advance +7 days", key="advance", use_container_width=True):
        wb.advance(7)
        st.rerun()
    reveal = st.checkbox("Reveal synthetic ground truth (demo only)", value=False)
    if st.button("Reset demo", key="reset", use_container_width=True):
        for k in ("wb", "opened_at", "case_select"):
            st.session_state.pop(k, None)
        st.rerun()

q = wb.queue(reveal)
n_watch = sum(1 for a in wb.watches if a not in wb.closed)
tab_q, tab_w, tab_r, tab_p, tab_a = st.tabs(
    ["🔎 Case queue", f"🛰️ Evidence Watch ({n_watch})", "📊 Reviewer quality", "🔌 PayPal Sandbox", "🧾 Audit log"])

# ------------------------------------------------------------- case queue
with tab_q:
    options = list(q.account)
    sel = st.session_state.get("case_select")
    if sel and sel not in options:
        options = [sel] + options
    if not options:
        st.success("No open cases on this day.")
    else:
        cols = ["account", "tier", "suspicion", "counter", "kind"] + (["synthetic_truth"] if reveal else [])
        st.dataframe(q[cols], use_container_width=True, hide_index=True)
        acct = st.selectbox("Open case", options, key="case_select")
        row = wb.case(acct)
        opened = st.session_state["opened_at"].setdefault((acct, wb.now), time.time())
        if row is None:
            st.info("No suspicious pattern detected for this account on this day.")
        else:
            st.markdown(f"### {acct} {badge(row.tier)}", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Suspicion", f"{row.suspicion:.2f}")
            m2.metric("Counter-evidence", f"{row.counter:.2f}")
            m3.metric("System recommends", row.tier)
            c_for, c_against = st.columns(2)
            with c_for:
                st.markdown("#### 🔴 Evidence for suspicion")
                for t in row.supporting:
                    st.markdown(f"- {t}")
            with c_against:
                st.markdown("#### 🟢 Evidence against")
                for t in (row.counter_evidence or ["No counter-evidence found."]):
                    st.markdown(f"- {t}")
            st.markdown("#### 🗺️ Money-flow map")
            day = st.slider("Replay: show the network as of day", max(0, wb.now - 30), wb.now, wb.now, key=f"replay_{acct}_{wb.now}")
            flow_map(acct, row.kind, day, row.tier)
            st.markdown("#### 🧮 Why this score")
            bd = breakdown(row)
            w1, w2 = st.columns(2)
            w1.markdown(f"**For suspicion = {bd['total_for']:.2f}**\n\n" + bars(bd["for_items"], "#D93025", bd["total_for"]), unsafe_allow_html=True)
            w2.markdown(f"**Against = {bd['total_against']:.2f}**\n\n" + bars(bd["against_items"], "#1E8E3E", max(bd["total_against"], 0.3)), unsafe_allow_html=True)
            for n_ in bd["notes"]:
                st.caption("ℹ️ " + n_)
            tier_, why = decision_path(float(row.suspicion), float(row.counter))
            st.markdown(f"**Decision path:** {why} → **{tier_}**")
            for line in what_would_change(float(row.suspicion), float(row.counter)):
                st.markdown(f"- {line}")
            with st.expander("🧠 Case summary (grounded in the evidence above)"):
                show_summary(f"case_{acct}_{wb.now}", facts_from_case(row))
            st.divider()
            ce = st.checkbox("I have read the counter-evidence", key=f"ce_{acct}_{wb.now}")
            reason = st.text_area("Written reason (required for every decision)", key=f"reason_{acct}_{wb.now}")
            with st.expander("🛰️ Evidence Watch settings (silent monitoring)", expanded=True):
                basis = st.selectbox("Basis", list(CAPS), key=f"basis_{acct}")
                dur = st.number_input("Duration (days)", 1, CAPS[basis], min(30, CAPS[basis]), key=f"dur_{acct}_{basis}")
                st.caption("A watch gathers evidence for AND against. It places no restriction on the account; "
                           "it expires automatically and every step is audited.")
            b1, b2, b3, b4 = st.columns([1, 1, 2, 1])
            seconds = time.time() - opened
            outcome = None
            if b1.button("✅ Clear", key="btn_clear", use_container_width=True):
                outcome = wb.decide_case(reviewer, acct, "Clear", reason, seconds, ce)
            if b2.button("❓ Verify", key="btn_verify", use_container_width=True):
                outcome = wb.decide_case(reviewer, acct, "Verify", reason, seconds, ce)
            if b4.button("🚨 Escalate", key="btn_escalate", use_container_width=True):
                outcome = wb.decide_case(reviewer, acct, "Escalate", reason, seconds, ce)
            if b3.button("🛰️ Start Evidence Watch", key="btn_watch", type="primary", use_container_width=True):
                try:
                    wb.start_watch(acct, basis, reason, reviewer, int(dur), seconds, ce)
                    st.toast("Evidence Watch started. See the Evidence Watch tab.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if outcome:
                (st.success if outcome[0] else st.error)(outcome[1])

# ----------------------------------------------------------- evidence watch
with tab_w:
    st.markdown("### Silent monitoring: evidence over time")
    st.caption("Each watch has a purpose, a limited duration and automatic expiry. Links to other accounts need real "
               "transfers with the watched account. The final decision is always the reviewer's.")
    if not wb.watches:
        st.info("No watches yet. Open a case and press **Start Evidence Watch**, or load a demo scenario.")
    for acct, w in wb.watches.items():
        status = wb.watch_status(acct)
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.markdown(f"### 🛰️ {acct} · {status.upper()}")
            left.caption(f"Basis: {w.ko.basis} · Purpose: {w.ko.purpose} · Day {w.ko.start_day} to {w.ko.end_day}")
            span = max(1, w.ko.end_day - w.ko.start_day)
            right.progress(min(1.0, max(0.0, (wb.now - w.ko.start_day) / span)),
                           text=f"{max(0, w.ko.end_day - wb.now)} days left")
            traj = wb.trajectory(acct)
            if len(traj) < 2:
                st.caption("Only one observation so far. Press “Advance +7 days” in the sidebar to watch the evidence evolve.")
            else:
                st.line_chart(traj.set_index("day")[["suspicion", "counter"]], color=["#D93025", "#1E8E3E"])
            p = wb.packet(acct)
            k1, k2, k3 = st.columns(3)
            k1.metric("Recommendation at start", p["start"]["tier"])
            dlt = p["now"]["suspicion"] - p["start"]["suspicion"]
            k2.metric("Recommendation now", p["now"]["tier"], None if abs(dlt) < 0.005 else f"{dlt:+.2f} suspicion")
            k3.metric("Counter-evidence now", f"{p['now']['counter']:.2f}")
            e1, e2 = st.columns(2)
            with e1:
                st.markdown("**🔴 For suspicion (now)**")
                for t in p["now"]["supporting"] or ["None"]:
                    st.markdown(f"- {t}")
            with e2:
                st.markdown("**🟢 Against (now)**")
                for t in p["now"]["counter_evidence"] or ["None"]:
                    st.markdown(f"- {t}")
            st.info(p["hint"])
            st.markdown("**🗺️ Watch the network form**")
            last = min(wb.now, w.ko.end_day - 1)
            if last > w.ko.start_day:
                wday = st.slider("Replay day", w.ko.start_day, last, last, key=f"wreplay_{acct}")
            else:
                wday = last
            case_now = wb.case(acct)
            flow_map(acct, case_now.kind if case_now is not None else "fan_in", wday, p["now"]["tier"])
            with st.expander("🧠 Watch summary (grounded in the evidence above)"):
                show_summary(f"watch_{acct}_{wb.now}", facts_from_packet(p, last - w.ko.start_day))
            st.markdown("**Linked accounts** (only accounts with real transfers; the reviewer approves each link)")
            for s in wb.link_suggestions(acct):
                c1, c2 = st.columns([4, 1])
                tag = "approved" if s["account"] in w.links else ("in-bank" if s["monitorable"] else "outside bank, not monitorable")
                c1.markdown(f"`{s['account']}` · {s['reason']} · *{tag}*")
                if s["monitorable"] and s["account"] not in w.links and c2.button("Approve", key=f"lnk_{acct}_{s['account']}"):
                    wb.approve_link(acct, s["account"], reviewer)
                    st.rerun()
            if p["linked"]:
                st.caption("Linked accounts now: " + ", ".join(f"{a}: {t}" for a, t in p["linked"].items()))
            if acct not in wb.closed:
                if status == "expired":
                    st.warning("Watch expired: evidence collection has stopped. Record a decision or open a new watch.")
                d_choice = st.radio("Decision", ["Clear", "Escalate", "Extend"], horizontal=True, key=f"wd_{acct}")
                d_reason = st.text_area("Written reason (required)", key=f"wr_{acct}")
                ext = st.number_input("Extend by (days)", 1, CAPS[w.ko.basis], 30, key=f"we_{acct}") if d_choice == "Extend" else 0
                if st.button("Record decision", key=f"wb_{acct}"):
                    try:
                        wb.decide_watch(acct, reviewer, d_choice, d_reason, int(ext))
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

# --------------------------------------------------------- reviewer quality
with tab_r:
    st.markdown("### Automation-bias guard")
    st.caption("Measures whether review is real review: agreement with the system, time per case, and whether the "
               "counter-evidence was opened. Thresholds are policy settings, not validated limits.")
    c1, c2 = st.columns(2)
    if c1.button("Simulate a rubber-stamping reviewer", key="sim_fast"):
        wb.simulate_reviewers("fast")
        st.rerun()
    if c2.button("Simulate a careful reviewer", key="sim_care"):
        wb.simulate_reviewers("careful")
        st.rerun()
    rep = wb.quality()
    if not rep:
        st.info("No reviews yet.")
    for who, r in rep.items():
        (st.error if r["possible_rubber_stamping"] else st.success)(
            f"**{who}**: {r['cases']} cases · agree {r['agreement']:.0%} · median {r['median_seconds']:.0f}s · "
            f"counter-evidence opened {r['counter_evidence_opened']:.0%}"
            + ("  →  POSSIBLE RUBBER-STAMPING" if r["possible_rubber_stamping"] else ""))
    if rep:
        st.dataframe(pd.DataFrame(rep).T, use_container_width=True)

# ------------------------------------------------------------ PayPal Sandbox
with tab_p:
    st.markdown("### PayPal Sandbox connection (read-only)")
    st.caption("Sandbox credentials only, kept in Streamlit Secrets. No real money and no real customers. "
               "Transactions can take up to 3 hours to appear in PayPal's Transaction Search.")
    try:
        creds = dict(st.secrets["paypal"])
    except Exception:
        creds = None
    if not creds:
        st.warning("No PayPal credentials found in Secrets. Add them in the app settings (see the README). "
                   "You can still try the offline sample below.")
    c1, c2, c3 = st.columns(3)
    if c1.button("1 · Connect to Sandbox", key="pp_connect", disabled=creds is None, use_container_width=True):
        try:
            st.session_state["pp"] = get_token(PayPalConfig(creds["client_id"], creds["client_secret"]))
            wb.audit.add(reviewer, "paypal_connected", "sandbox", {"search_scope": st.session_state["pp"]["has_search_scope"]}, wb.now)
        except Exception as e:
            st.error(str(e))
    pp = st.session_state.get("pp")
    if pp:
        st.success(f"Connected to PayPal Sandbox. Token valid for about {pp['expires_in'] // 3600} hours.")
        if not pp["has_search_scope"]:
            st.warning("This token does not include the Transaction Search scope. Enable 'Transaction Search' for the "
                       "sandbox app in the PayPal developer dashboard (it can take hours to activate).")
    if c2.button("2 · Fetch last 30 days", key="pp_fetch", disabled=not pp, use_container_width=True):
        try:
            details, holder, start = fetch_last_days(PayPalConfig(creds["client_id"], creds["client_secret"]), pp["token"], 30)
            edges, skipped = to_edges(details, holder, default_origin(start))
            st.session_state["pp_data"] = dict(edges=edges, skipped=skipped, raw=len(details), source="live PayPal Sandbox")
            wb.audit.add(reviewer, "paypal_fetch", "sandbox", {"records": len(details), "used": len(edges)}, wb.now)
        except Exception as e:
            st.error(str(e))
    if c3.button("Use offline sample (not live)", key="pp_sample", use_container_width=True):
        from datetime import datetime, timezone
        start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        edges, skipped = to_edges(SAMPLE_RESPONSE["transaction_details"], SAMPLE_RESPONSE["account_number"], default_origin(start))
        st.session_state["pp_data"] = dict(edges=edges, skipped=skipped, raw=len(SAMPLE_RESPONSE["transaction_details"]),
                                           source="offline sample in PayPal's format (NOT a live call)")
    data = st.session_state.get("pp_data")
    if data:
        edges = data["edges"]
        st.info(f"Source: {data['source']}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Records received", data["raw"])
        m2.metric("Used for analysis", len(edges))
        m3.metric("Counterparties", len(set(edges.src) | set(edges.dst)) - 1 if len(edges) else 0)
        if any(data["skipped"].values()):
            st.caption(f"Skipped: {data['skipped']}")
        if edges.empty:
            st.info("No completed USD transactions in this window yet. Send a few test payments between your sandbox accounts "
                    "and try again later.")
        else:
            st.dataframe(edges, use_container_width=True, hide_index=True)
            if st.button("3 · Analyze with AML-Nexus", key="pp_analyze"):
                res = analyze(edges)
                if res.empty:
                    st.success("No suspicious pattern in this feed. (A small sandbox feed rarely has one; the demo "
                               "scenarios use synthetic data.)")
                else:
                    st.dataframe(res[["account", "tier", "suspicion", "counter", "kind"]], use_container_width=True, hide_index=True)
                    for _, r in res.iterrows():
                        st.markdown(f"**{r.account}** {badge(r.tier)}", unsafe_allow_html=True)
                        st.markdown("- " + "\n- ".join(r.supporting))
                st.caption("PayPal does not expose account age, so age-based signals are neutral on live data. "
                           "Direction is inferred from the sign of each amount.")

# ---------------------------------------------------------------- audit log
with tab_a:
    st.markdown("### Tamper-evident audit log")
    (st.success if wb.audit.verify() else st.error)(
        "Hash chain valid" if wb.audit.verify() else "Hash chain BROKEN: entries were altered")
    if wb.audit.entries:
        df = pd.DataFrame(wb.audit.entries)
        df["detail"] = df["detail"].map(lambda d: json.dumps(d, default=str))
        st.dataframe(df[["seq", "day", "actor", "action", "subject", "detail"]], use_container_width=True, hide_index=True)
    else:
        st.info("No entries yet.")
