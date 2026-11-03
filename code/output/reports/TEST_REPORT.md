# Test Report

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows (win32) |
| Python | 3.10.11 |
| FastAPI | 0.115.0 |
| Uvicorn | 0.30.6 |
| httpx | 0.28.1 |
| Pydantic | 2.9.2 |
| Node.js | v24.12.0 |
| Test framework | stdlib `unittest` (pytest not installed) |
| Cloud services used | None |

## 2. Commands and results

```powershell
cd "C:\projects\azure prototype\code"
python -m unittest discover -s cwms_tests -t . -v
python -m compileall -q cwms_simulator cwms_api cwms_scripts cwms_tests
node --check cwms_dashboard/app.js
```

| Check | Result |
|---|---|
| Unit + integration suite | **187 tests run, OK** (4.078 s) |
| Python compile check | OK |
| Dashboard JS syntax | OK |
| CLI valid run | Exit 0, CSV/JSON written |
| CLI admission run | Produced queued, overflow, and timed-out requests |
| CLI invalid config (`burst_end > intervals`) | Exit 2, message `burst_end cannot exceed intervals` |
| Experiment rerun | 80 runs (5 seeds), summary and 95% CIs reproducible |
| Accounting check | 80/80 rows satisfy generated = accepted + rejected and accepted = completed + failed |
| Browser smoke test | Pass: `Browser smoke passed: 20 forecast rows; overload=1344, timeouts=296` |
| Live API smoke | Pass: auth 401/200, 413 body limit, overload run, history prune |
| History prune CLI | Dry-run reported database state correctly |

## 3. Coverage by module

| Module | What is verified |
|---|---|
| `nodes.py` | Name/capacity validation, health transitions, assignment, load cap, decay, admission accept/queue/overflow, zero queue, unhealthy, queue reset, serialization |
| `policies.py` | Round-robin skipping unhealthy nodes, least-loaded selection, FCFS behavior, adaptive forecast/capacity branch, saturation tie-breaking by assignment count, factory errors |
| `traffic_generator.py` | Seed reproducibility, burst window boundaries, variation range, scenario defaults |
| `metrics.py` | Counters, completion/rejection/failure/queue/timeout rates, rejection-reason validation, interval reset, health sync |
| `surge_detector.py` | Rate/average/max-load triggers and priority, cooldown, reset, serialization, below-threshold behavior |
| `forecaster.py` | Moving-average and change-aware strategies, windowing, MAE/RMSE, first-interval exclusion, MA/naive baselines, error handling |
| `recommendations.py` | Every rule, severity, no-action case, latest recommendation |
| `storage.py` | Schema creation, v2 admission fields roundtrip, ordering, persistence across instances, missing IDs, pruning, v1-to-v2 migration |
| `simulator.py` | Normal/burst/failure/overload runs, unhealthy node assignment, policy equivalence, no-leak forecasting, forecast-strategy and MA/naive fields, max-load detection, CSV/JSON exports, overflow/timeout accounting, disabled admission, config validation |
| `test_api.py` | Health/config, start/status/results/summary, scenario validation incl. overload, 400/404/409/422 paths, exports, history/pruning, dashboard/assets, persistence, bearer auth, 413, security headers, CORS parser, remote-bind guard, volume cap |
| `test_dashboard_assets.py` | Required element IDs, policy options, simulated-data label, theme variables, static asset paths, token control, admission fields, fourth scenario card |

API tests use `TestClient` with temporary SQLite databases; they do not write the
development database.

## 4. Live API smoke

Started `python run_api.py` as a separate Uvicorn process on an isolated port and
temporary database with `CWMS_API_TOKEN` set, then used HTTP requests:

| Request | Observed |
|---|---|
| `GET /health` | `200`, `healthy`, `nosniff` header |
| `GET /api/config` | `200`, `auth_required=true`, `overload` advertised |
| `POST /api/scenarios/run` without token | `401` |
| Oversized JSON body (`~40 KB`) with token | `413` |
| `POST /api/scenarios/run` overload with token | `200` |
| Poll status | Finished without error |
| `GET /api/simulation/summary` | queued 556, overload rejections 1344, timeouts 296; accounting identity holds |
| `POST /api/history/prune` without token | `401` |
| `POST /api/history/prune` with token | `200`, run deleted |

Server stderr contained only normal Uvicorn startup logs; no tracebacks. The
isolated smoke database stayed outside the project and was not packaged.

### Browser smoke test

`cwms_scripts/browser_smoke.py` launched the API on an isolated port/database and
drove installed Microsoft Edge through Playwright. It ran the normal scenario,
verified 20 forecast rows and no page errors, then ran the overload scenario and
waited for visible `Rejected: Overload` and failed/timeout counts. Result:
`Browser smoke passed: 20 forecast rows; overload=1344, timeouts=296`.
This is a single-browser smoke test, not a cross-browser or accessibility audit.

## 5. Bugs found and fixed

Earlier passes fixed console encoding, forecast leakage, surge cooldown, missing
status metadata, event-loop blocking, burst validation, CORS wildcard+credentials,
asset paths, the misleading stop endpoint, stale node health, CLI inconsistency,
config validation drift, chart offline failure, health-toggle 422, health toggles
before the first run, startup status races, saturation tie-breaking, chart
double-counting, unsupported `custom` scenario, invalid README example, missing
naive baseline, running-status metadata, max-load surge blind spot, lagging burst
forecast, and weak experiment uncertainty.

This pass fixed/added:

1. **No admission outcomes** - overload previously raised latency/load without
   rejecting or timing out work. Added bounded queues, overflow rejection, and
   timeout failures.
2. **Admission accounting gaps** - propagated accepted/queued/completed/failed/
   timed-out/rejection-reason fields through metrics, simulator, CSV, SQLite, API,
   dashboard, and experiment.
3. **Unbounded API exposure** - added body and volume caps, optional bearer auth,
   remote-bind guard, opt-in CORS, security headers, and generic background errors.
4. **CORS helper shadowing** - a middleware variable shadowed `_cors_origins()`;
   renamed it so tests and runtime use the same helper.
5. **Prune route ambiguity** - declared `/api/history/prune` before
   `/api/history/{run_id}`.
6. **Stale schema** - added schema v2, idempotent migration, WAL/busy timeout, and
   pruning.
7. **Dashboard gaps** - added token entry, admission controls, queue/overflow
   columns, expanded metrics, and overload scenario card.
8. **Packaging** - excluded SQLite WAL/SHM sidecars.

## 6. Not tested / not run

- Cross-browser coverage; the optional Playwright smoke test uses installed
  Microsoft Edge only.
- Screen-reader or accessibility audit.
- Load/soak/concurrency testing; runs are single-process and one-active-run.
- Real Azure deployment, real telemetry ingestion, cost behavior.
- Statistical significance testing; five seeds provide 95% confidence intervals
  and a repeatability check, not a hypothesis test.
- Production queue semantics; wait is an estimate and queues drain once per
  interval.
- TLS, reverse-proxy integration, multi-user authorization, rate limiting, or
  audit logging.
- Malicious-input fuzzing beyond API validation/auth/limit tests.

## 7. Residual risks

- The dashboard may render differently across browsers; Chart.js requires the
  CDN unless cached.
- The shared bearer token has no rotation/revocation, and serving beyond localhost
  requires an external TLS/identity layer.
- Queue wait, timeout, and completion are synthetic; they are not production SLO
  evidence.
- Surge thresholds are heuristic and unlabelled; max-load detection is verified
  by behavior, not precision/recall.
- SQLite is single-writer; WAL improves read/write tolerance but is not HA.
- The overload scenario is deliberately artificial; results do not establish a
  generally superior policy.

## 8. Conclusion

The implemented scope passes its automated suite and local integration checks,
including auth/limit paths and a real browser run of both normal and overload
scenarios. Accounting identities hold across all 80 experiment runs. Claims are
limited to the tested local simulation.
