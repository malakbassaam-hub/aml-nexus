# Roadmap: status against the development plan

AML-Nexus is a hackathon prototype on synthetic data. Nothing here is bank-approved or production-ready, and nothing below should be read as a claim of validated performance.
**Done** = implemented and tested. **Partial** = some of it exists. **Planned** = after the hackathon. **Not code** = business or legal work.

| # | Item | Status | What exists today / what is missing |
|---|---|---|---|
| 1 | Transaction network analysis | Partial | Fan-in, slow accumulation into young accounts, closed loops, flow map with replay. Missing: fan-out, centrality, multi-hop layering, aged-account scenarios. |
| 2 | Explainable risk engine | Partial | Exact score breakdown, decision path, statistical second opinion. Missing: uncertainty, calibration, per-decision model versions. |
| 3 | Evidence for and against | Partial | Both lists, with "not yet observable" treated as neutral. Missing: confidence, source, timestamp, dependencies, missing-evidence list. |
| 4 | Advanced statistical detection | Partial | Peer-relative Benford check. Missing: suitability tests, more indicators, broader sensitivity analysis. |
| 5 | False-positive reduction | Partial | Counter-evidence gating measured on held-out runs. Missing: interactive lab. |
| 6 | Human-in-the-loop decisions | Partial | Four tiers, written reason, escalation blocked until counter-evidence is read, audit trail. Missing: second review, reopen, override logging. |
| 7 | Silent monitoring | Partial | Purpose, duration cap, review cadence, extension with reason, auto-expiry, audited. Missing: alerts on new evidence, retention rules. |
| 8 | Counterfactual analysis | Done (score level) | "What would change the recommendation". |
| 9 | Risk timeline | Partial | Watch trajectory chart and replay. Missing: decisions overlaid. |
| 10 | Case management | Planned | Only a case queue today. |
| 11 | Investigation reports | Partial | Printable HTML report with a SHA-256 fingerprint (Print, then Save as PDF). Native PDF is planned. |
| 12 | Tamper-evident audit trail | Partial | Hash chain with tests, held in memory. Missing: persistent trusted storage. |
| 13 | Performance dashboard | Partial | Evaluation tab (detection, innocents flagged, per run). Missing: precision, F1, confusion matrix, latency. |
| 14 | False-positive lab | Planned | |
| 15 | Security hardening | Partial | Secrets kept out of the repo, sandbox-only PayPal client, escaped report output. Missing: Bandit, CodeQL, pip-audit runs. |
| 16 | Authentication and roles | Planned | |
| 17 | Data privacy and protection | Planned | Only synthetic data is used; no customer data is sent to AI services. |
| 18 | REST API | Planned | |
| 19 | Data import and validation | Planned | |
| 20 | Configurable risk policies | Planned | |
| 21 | Scalability | Planned | |
| 22 | Reliable deployment (Docker) | Planned | |
| 23 | Case simulation studio | Partial | Seeded generator; no interface. |
| 24 | Human vs AI comparison | Partial | Reviewer-quality guard. No controlled experiment. |
| 25 | Investigation copilot | Partial | Optional LLM summaries that only restate the evidence, with a number check. |
| 26 | Evidence provenance | Planned | |
| 27 | Model drift monitoring | Planned | |
| 28 | Independent benchmarking | Partial | Held-out synthetic runs. Same authors wrote data and detectors; no external benchmark. |
| 29 | Automated testing | Partial | Unit and integration tests run on every push. No security, permission or load tests yet. |
| 30 | Reproducible evaluation | Partial | Fixed seeds and scripts. Missing: pinned versions, confidence intervals. |
| 31 | IP and licensing review | Not code | Code is published under MIT; a commercial version would need a fresh review. |
| 32 | Enterprise documentation | Partial | README, this roadmap, known limits. |
| 33 | Professional demonstration | Partial | Five scripted scenarios in the app. |
| 34 | Paid proof-of-concept package | Not code | |
| 35 | Commercial licensing and pricing | Not code | |
| 36 | Professional UI/UX | Partial | |
| 37 | Executive dashboard | Planned | |

## Working rules
Review existing code before adding features; small tested steps; no invented performance figures; synthetic or authorised data only; no automatic freezing; secrets never in the repo; document unresolved problems rather than hiding them.
