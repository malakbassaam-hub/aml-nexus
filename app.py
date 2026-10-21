"""AML-Nexus dashboard.  Run:  streamlit run app.py
All data is synthetic. The system recommends; a human decides."""
import json
import time

import pandas as pd
import streamlit as st

from src.service import SCENARIOS, TIER_COLORS, Workbench
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
wb = st.session_state["wb"]


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
tab_q, tab_w, tab_r, tab_a = st.tabs(
    ["🔎 Case queue", f"🛰️ Evidence Watch ({n_watch})", "📊 Reviewer quality", "🧾 Audit log"])

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
            st.line_chart(traj.set_index("day")[["suspicion", "counter"]], color=["#D93025", "#1E8E3E"])
            p = wb.packet(acct)
            k1, k2, k3 = st.columns(3)
            k1.metric("Recommendation at start", p["start"]["tier"])
            k2.metric("Recommendation now", p["now"]["tier"],
                      f"{p['now']['suspicion'] - p['start']['suspicion']:+.2f} suspicion")
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
