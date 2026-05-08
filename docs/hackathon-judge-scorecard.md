# Hackathon Judge Scorecard

This scorecard expands the official Colosseum/Solana judging dimensions into a 20-criteria review surface: Functionality, Potential Impact, Novelty, UX, Open-source/composability, and Business Plan.

Scale: 1 poor, 2 weak, 3 acceptable, 4 strong, 5 exceptional.

Current post-hardening target score: 82/100.

| # | Area | Criterion | Score | Evidence | Improvement |
|---|---|---|---:|---|---|
| 1 | Functionality | API works in sample mode | 5 | `/healthz`, `/v0/status`, and dashboard summary can run fixture-backed. | Add hosted demo URL when available. |
| 2 | Functionality | Dashboard builds and renders useful evidence | 4 | Vite build and API-unreachable state exist. | Add browser screenshot evidence. |
| 3 | Functionality | Unit coverage and phase harness | 5 | 150+ unit tests plus phase targets. | Add CI badge after GitHub publish. |
| 4 | Functionality | Secure orchestration defaults | 4 | `/internal/run` fails closed without token. | Add Cloud Run IAM proof in deployment evidence. |
| 5 | Potential Impact | Clear Solana/x402 problem relevance | 4 | README and integration docs frame route evidence for Solana/x402. | Add concrete user story from a builder. |
| 6 | Potential Impact | Market/business relevance | 4 | Paid proxy and operator manual describe monetizable evidence access. | Add pricing rationale and TAM assumptions. |
| 7 | Potential Impact | Solana ecosystem impact | 4 | Sample fixture and adapter center Solana stablecoin evidence. | Connect a live indexer after hackathon. |
| 8 | Potential Impact | Agent/decision-layer usefulness | 4 | Decision-layer guide and route-policy surface exist. | Add example agent consuming outputs. |
| 9 | Novelty | x402 evidence benchmark framing | 4 | Separates benchmark evidence from payment execution. | Add comparison against existing explorer dashboards. |
| 10 | Novelty | Generic adapter extensibility | 5 | Fixture source and adapter contract support external inputs. | Add BigQuery adapter example. |
| 11 | Novelty | Paid route-policy surface | 4 | AgentCash-compatible route-policy proxy is documented as optional. | Add verifier sandbox walkthrough. |
| 12 | Novelty | Methodology differentiation | 4 | Dark Factory PDF and retrospective artifacts are included. | Add concise methodology diagram. |
| 13 | UX | Dashboard clarity | 4 | Evidence console and setup failure copy exist. | Add recorded demo flow. |
| 14 | UX | API failure/setup guidance | 4 | README, operator manual, and runbook cover sample setup. | Add one-command local demo target. |
| 15 | UX | Operator onboarding | 4 | Operator manual covers sample mode, Cloud Run, BigQuery, AgentCash. | Add cloud deploy screenshots. |
| 16 | UX | Demo simplicity | 4 | Fixture mode avoids required credentials. | Add Docker Compose if time allows. |
| 17 | Open-source/composability | License/security/readme quality | 5 | MIT, SECURITY, README, AGENTS, and grep gates exist. | Add contribution guide. |
| 18 | Open-source/composability | Composability with external data | 5 | Data and decision layer docs define row shape and adapter contract. | Add schema examples per source. |
| 19 | Open-source/composability | CI/reproducibility | 4 | CI workflow and dashboard lockfile are present. | Publish GitHub Actions results. |
| 20 | Business Plan | Deployment and operations plan | 4 | Premortem and operator manual cover deploy dependencies. | Add go-to-market milestone table. |

## Highest-Leverage Remaining Work

- Publish CI results and a hosted demo.
- Add a BigQuery adapter example that reads from `YOUR_PROJECT_ID.YOUR_DATASET`.
- Add a short agent example calling `/v0/dashboard-summary` and optional `POST /v1/route-policy`.
- Record a 90-second judge walkthrough covering sample mode, paid proxy boundary, and decision-layer handoff.
