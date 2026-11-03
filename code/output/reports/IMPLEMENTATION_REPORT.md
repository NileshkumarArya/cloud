# Implementation Report

## 1. Executive summary

A complete local CWMS prototype was implemented inside `code/`: a synthetic
workload simulator, four scheduling policies, bounded admission queues with
overflow rejection and simulated timeouts, metrics, rate/average/max-load surge
detection, causal moving-average and change-aware forecasters, rule-based
recommendations, CSV/JSON export, versioned SQLite history, a FastAPI backend
with optional bearer auth and resource limits, a web dashboard, automated tests,
and a reproducible policy-comparison experiment.

The final test suite passes, the JavaScript passes `node --check`, the CLI
validates invalid configurations, the API was smoke-tested as a real Uvicorn
process, and the dashboard passed a headless Edge smoke test. No Azure resource
was created and all values are clearly labeled as simulated.

## 2. Scope and constraints

- Source requirements: supplied document pack `01`-`10` plus the build brief.
- Environment: Windows 10/11, Python 3.10.11, FastAPI 0.115.0, Uvicorn 0.30.6,
  httpx 0.28.1, Pydantic 2.9.2, Node.js v24.12.0 (syntax check only).
- No paid cloud operations, no credentials, no production traffic.
- Original documents and the supplied ZIP outside `code/` were not modified.
- The API is a local demonstration; the optional token is not a full auth system.

## 3. Delivered functionality

### Simulation core

- Three simulated nodes: `backend-a` (100), `backend-b` (100), `backend-c` (75).
- Request generation with seeded +/-10% variation and configurable burst window.
- Load decay, per-request load addition, 150% cap, and load-dependent simulated
  latency.
- Health state; unhealthy nodes receive no new assignments.
- Policies: round-robin and least-loaded (documented), FCFS and adaptive
  (build-brief extensions).
- Bounded per-node admission queues above `overload_threshold`; overflow
  rejection when `queue_limit` is reached.
- Queued wait estimated from capacity and queue position; requests exceeding
  `request_timeout_ms` fail as timeouts instead of completing.
- Admission can be disabled to reproduce the legacy immediate-completion path.
- Per-interval results, surge events, forecasts, recommendations, and summary.

### Analytics

- Rate surge (average request count), average-load surge, and maximum-node-load
  surge, with priority `rate > max_load > average_load` and a 2-interval cooldown.
- Causal moving-average and change-aware strategies over prior intervals only.
  Change-aware uses the latest observation when recent spread exceeds 20% of the
  mean; MA, selected-strategy, and naive MAE/RMSE are exported and compared.
- Rule-based recommendations for overload, surge, imbalance, unhealthy nodes,
  and sustained low load.
- System counters distinguish generated, accepted (immediate + queued),
  completed, failed/timed-out, queued, and rejected-overload/no-capacity.

### Interfaces

- CLI with validation, quiet mode, forecast/max-load options, admission flags,
  and CSV/JSON export.
- REST API: run control, scenarios including `overload`, status/results/summary,
  node health, CSV/JSON export, SQLite history, authenticated pruning, and static
  dashboard.
- Dashboard: overview cards, node table with queue/overflow columns, metrics
  table, forecast table, scenario launcher including overload, policy selection,
  admission settings, optional API token, loading/error states, simulated-data
  badge.
- No fake stop endpoint; the UI does not claim cancellation support.

### Persistence

- SQLite tables `runs`, `interval_metrics`, `node_metrics`, foreign keys with
  cascade, `PRAGMA user_version=2`, WAL journal mode, busy timeout.
- Idempotent v1-to-v2 migration adds admission/queue/failure columns with safe
  defaults.
- API writes each completed run in a single transaction and exposes it through
  history endpoints. `prune_runs()` and a CLI/API path enforce retention.

### Security and resource bounds

- Loopback bind by default; non-loopback bind refused without a token or explicit
  override.
- Optional `CWMS_API_TOKEN` bearer auth on state-changing endpoints.
- 32 KiB body limit (including chunked requests), 100,000 generated-request cap,
  intervals <=200, rates <=1000.
- CORS disabled unless `CWMS_CORS_ORIGINS` is set.
- Security headers and generic background error responses.
- Dashboard token kept in session storage only.

### Experiment and documentation

- 80-run experiment: 4 scenarios x 4 policies x 5 seeds, identical input per
  seed, with t-based 95% confidence intervals.
- Overload scenario uses threshold 80, queue 10, timeout 100 ms to exercise
  overflow and timeouts.
- Reports generated automatically in `output/reports/`.
- README, architecture, API reference, testing guide, security notes, Azure plan,
  requirements traceability, and output documentation updated.

## 4. Data flow

1. Traffic generator produces a count per interval.
2. Node loads decay; the selected policy picks a healthy node.
3. Admission accepts immediately, queues, or rejects as overload.
4. Queued requests drain at interval end; wait over timeout fails.
5. Metrics record accepted/completed/failed/queued/rejection reasons and load.
6. Surge detection runs on request rate, average load, and maximum node load.
7. Forecaster predicts from prior observations only using the selected strategy.
8. Recommendation rules evaluate the current state.
9. Interval results and final summaries are exported and/or persisted.

## 5. Key implementation decisions

| Decision | Reason | Consequence |
|---|---|---|
| Stdlib simulation core | Matches docs and avoids heavy dependencies | Easy to run and audit |
| FCFS/adaptive added | Explicit build-brief comparison | Labeled extensions, not documented baseline |
| Bounded per-interval queue | Make overload outcomes explicit without a full queueing engine | Wait is an estimate, not discrete-event |
| Timeout as only failure reason | Simple, testable SLO analogue | No network/retry failure modelling |
| Schema v2 with in-place migration | Preserve existing local history | Adds columns; no external migration framework |
| WAL + busy timeout | Better tolerance for reads during writes | Still single-writer SQLite, not HA |
| Optional shared token | Prevent casual unauthenticated remote control | Not multi-user authorization |
| Opt-in CORS | Avoid accidental browser exposure | Cross-origin clients must configure origins |
| Vanilla HTML/CSS/JS | No build step for a small dashboard | Chart.js via CDN; static tests only |
| `unittest` | pytest unavailable in environment | Tests run without extra install |
| Adaptive capacity-first mode | Uses forecast to prefer headroom over balance | Not a general win; measured trade-offs |
| Fair tie-breaking | Prevents saturation from concentrating on one node | Load/headroom ties go to fewer prior assignments |
| Change-aware forecast default | Pure MA lagged burst onset | Burst MAE falls from 45.06 to 18.56, close to naive 19.09 |
| Maximum-load detection | Average-load rule missed FCFS concentration | FCFS normal runs now raise 9 alerts; thresholds remain heuristic |

## 6. Verification performed

| Check | Result |
|---|---|
| `python -m unittest discover -s cwms_tests -t .` | 187 tests, OK |
| `python -m compileall` on simulator/API/scripts/tests | OK |
| `node --check cwms_dashboard/app.js` | OK |
| CLI invalid burst bounds | Exit 2 with clear message |
| CLI admission run | Produced queued, overflow, and timed-out requests |
| Real Uvicorn smoke test | Health, scenarios, pre-run health toggle, immediate status, dashboard, failed-node override all pass |
| Browser smoke test | Headless Edge pass; 20 forecast rows rendered |
| Experiment rerun | 80 runs; summary and 95% CIs reproducible |
| History pruning | CLI dry-run/API tests pass; v1 migration test passes |
| ZIP extraction check | Performed after packaging; see `PACKAGING_REPORT.md` |

Detailed evidence: `TEST_REPORT.md`; experiment analysis:
`RESEARCH_EVALUATION_REPORT.md`; audit: `AUDIT_REPORT.md`.

## 7. Defects found and fixed during implementation

Earlier passes fixed console encoding, forecast leakage, surge cooldown,
event-loop blocking, burst validation, CORS wildcard+credentials, asset paths,
stale health, policy/fail-node validation, chart double-counting, missing naive
baseline, max-load blind spot, forecast lag, saturation tie-breaking, and
documentation drift.

This pass fixed/added:

- Admission accounting across simulator, metrics, CSV, storage, API, dashboard.
- Queue overflow and timeout handling; timeout never counted as completion.
- API body/volume limits, optional bearer auth, bind guard, opt-in CORS,
  security headers, generic background errors.
- SQLite schema v2 migration, WAL/busy timeout, and history pruning.
- Broken test due to a CORS helper variable name shadowing; renamed.
- Prune route ordering before the dynamic history route.
- Dashboard token/admission controls and fourth scenario card.
- Packaging exclusions for SQLite WAL/SHM sidecars.
- README/API/architecture/testing/traceability/security/report synchronization.

## 8. Known limitations

- Synthetic node load/latency only; no real CPU, RAM, or Azure telemetry.
- Queue wait is an estimate; queues drain once per interval and do not persist.
- Timeout is the only failure reason; no network errors, retries, or SLO policy.
- No autoscaling, distributed workers, TLS, rate limiting, or multi-user auth.
- Surge detection is threshold-based; no labelled precision/recall.
- Change-aware forecast is a simple causal rule, not ML.
- Adaptive is not a general measured win; overload results show a completion-vs-
  acceptance trade-off, not dominance.
- Five seeds and 95% confidence intervals support repeatability, not formal
  statistical significance.
- Browser smoke coverage is single-browser (Edge), not cross-browser or
  accessibility testing.
- No Azure deployment, cost claim, or production-readiness claim is made.

## 9. Compliance and safety

- No secrets, credentials, subscription IDs, or personal data introduced.
- No shell execution from API input; node names and run IDs are constrained.
- Safe local defaults; remote exposure requires explicit configuration.
- Original documentation pack untouched; all changes are inside `code/`.
- Azure remains blocked pending pricing review and owner approval.

## 10. Final status

The local prototype is complete and runnable. Azure work remains explicitly
blocked pending pricing review and owner approval, as required by the source
documents.
