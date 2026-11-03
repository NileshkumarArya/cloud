# Audit Report

## 1. Scope

Fourth-pass audit of the local CWMS prototype after adding bounded admission
control, simulated timeouts, API hardening, schema migration/pruning, and an
expanded experiment. The audit covered:

- Simulator accounting under queueing, overflow, timeouts, and disabled admission.
- Policy behavior and result interpretation.
- API auth, CORS, bind guard, body/volume limits, and error exposure.
- Dashboard/API integration for admission fields, token entry, and new metrics.
- SQLite v1-to-v2 migration, new columns, and pruning.
- Documentation, reports, test count, and packaging consistency.

No Azure resource was created, started, resized, or billed. All findings are in
the local synthetic prototype.

## 2. Method

1. Re-read the simulator, policies, API, dashboard, exports, tests, and reports.
2. Ran focused simulations for normal, burst, failure, overload, disabled
   admission, zero queue, and low timeout.
3. Exercised the API through `TestClient` and a real Uvicorn + headless Edge
   browser smoke run.
4. Checked accounting identities and per-node totals across all 80 experiment
   runs.
5. Ran the full suite, Python compile check, and JavaScript syntax check.
6. Rebuilt and verified the archive from a fresh extraction.

## 3. Findings and fixes in this pass

### B1. Overload raised latency without explicit outcomes

- **Finding:** the earlier model had no admission control. At overload, requests
  were still assigned and immediately completed; only latency/load rose. This made
  completion and rejection useless for overload analysis.
- **Fix:** added per-node `overload_threshold`, `queue_limit`, and per-interval
  queue admission. Requests resolve to accepted, queued, overflow-rejected, or
  no-capacity-rejected.
- **Evidence:** `nodes.py` (`admit_request`, `reset_queue`), simulator queue
  drain, `test_nodes.py`, `test_simulator.py`, overload scenario.

### B2. Queue wait had no timeout consequence

- **Finding:** without a timeout, a full queue could hold work indefinitely or
  count queued work as completed regardless of wait.
- **Fix:** estimated queue wait is `1000 / max(1, capacity) * position +
  simulated latency`. If it exceeds `request_timeout_ms`, the request is recorded
  as failed/timed-out and never completed.
- **Evidence:** `_finish_request`, queue-drain logic, timeout tests, overload
  experiment.

### B3. Admission accounting could diverge across layers

- **Finding:** metrics, interval results, CSV, SQLite, API status, summary, and
  dashboard all needed the same accepted/queued/completed/failed/rejected
  breakdown.
- **Fix:** added explicit fields end to end and tests for the identities
  `generated = accepted + rejected` and `accepted = completed + failed`. A
  dedicated test also asserts every overload rejection is reason-tagged.
- **Evidence:** `metrics.py`, `simulator.py`, `storage.py`, `main.py`, dashboard,
  `test_metrics.py`, `test_simulator.py`, `test_storage.py`, `test_api.py`.

### B4. Unbounded API resource use and unsafe defaults

- **Finding:** the API accepted very large interval/rate combinations, any body
  size, any CORS origin, and could bind remotely without authentication.
- **Fix:** intervals <=200, rates <=1000, total generated requests <=100,000,
  body <=32 KiB, CORS opt-in, loopback default, remote-bind guard, and optional
  bearer token for all state-changing endpoints. Background errors are generic.
- **Evidence:** `cwms_api/main.py`, `TestSecurity`, security headers test, bind
  guard test, `.env.example`, `SECURITY.md`.

### B5. Dashboard did not expose admission state or token entry

- **Finding:** the dashboard had no token field, no admission controls, and no
  queue/overflow columns.
- **Fix:** added a session-storage token field, Authorization headers for
  protected POSTs, admission settings in the custom form, queue/overflow node
  columns, and expanded accepted/completed/failed/queued/rejected summary cards.
- **Evidence:** `index.html`, `app.js`, `styles.css`, dashboard asset tests,
  headless Edge smoke.

### B6. History schema and retention were stale

- **Finding:** the database schema did not store the new fields, had no migration
  path, and had no retention control.
- **Fix:** schema version 2 with idempotent column migration, WAL journal mode,
  busy timeout, and `prune_runs(keep_latest)` plus CLI and authenticated API
  endpoints.
- **Evidence:** `storage.py`, v1-migration test, prune tests, `prune_history.py`,
  `/api/history/prune`.

### B7. Experiment did not exercise overload or timeouts

- **Finding:** the 60-run experiment used only normal/burst/failure, so the new
  admission behavior was untested at the research level.
- **Fix:** added an `overload` scenario (base 120, threshold 80, queue 10,
  timeout 100 ms) and expanded to 80 runs. All metrics remain per-seed, with 95%
  confidence intervals where meaningful.
- **Result:** all 80 runs satisfy the accounting identities; overload produced
  both overflow rejections and timeouts. See `RESEARCH_EVALUATION_REPORT.md`.

### B8. Documentation drift

- **Finding:** README, API reference, architecture, testing, traceability, and
  reports still described 157 tests, 60 runs, no admission control, permissive
  CORS, and no auth.
- **Fix:** updated all documents and reports, including explicit residual risks
  and the new 80-run results. Counts and limitations were re-checked against the
  code and test output.

### B9. Smaller correctness fixes

- Fixed a test-environment shadowing issue where a CORS middleware variable could
  hide the `_cors_origins()` helper; renamed the configured-origins variable.
- Ensured history-prune route is declared before `/api/history/{run_id}` so
  `prune` is not parsed as a run ID.
- Added dashboard static tests for token and admission controls and the fourth
  scenario card.
- Excluded SQLite WAL/SHM sidecars from packaging.

## 4. Final verification

| Check | Result |
|---|---|
| Full suite | 187 tests, OK (recorded in `TEST_REPORT.md`) |
| Python compile | OK |
| JavaScript syntax | OK |
| Experiment | 80 runs; accounting identities hold |
| Live browser | Headless Edge pass; 20 forecast rows rendered |
| CLI admission flags | 2-interval overload run produced queued, overflow, and timed-out requests |
| Prune CLI | Dry-run reported database state correctly |
| History API | Prune protected by token when enabled; keeps newest N |
| Admission-disabled path | Returns to immediate completion; regression test passes |
| ZIP | Integrity/contents/extracted tests verified after rebuild |

## 5. Residual issues

- Queue wait is an estimate from capacity and position, not a discrete-event
  queue; it drains once per interval.
- Timeout is the only failure reason; there is no network error or retry model.
- Admission helps bound outcomes, but no autoscaling or SLO policy consumes the
  recommendations.
- Surge detection remains threshold-based with no labelled precision/recall.
- Five seeds and 95% confidence intervals are not a formal significance test.
- Auth is a shared bearer token, not multi-user authorization; no TLS, rate
  limiting, or audit log.
- Browser coverage is a single-browser smoke test, not cross-browser or
  accessibility testing.
- No load/soak/concurrency testing and no Azure deployment or billing.

## 6. Conclusion

The admission-control pass changed the system from "all accepted work completes"
to an explicit model of queueing, overflow, and timeouts, with consistent
accounting through simulation, storage, API, dashboard, and experiment. The
security and retention gaps were also addressed within the local scope. Remaining
limitations are explicit and are not hidden by the passing suite.
