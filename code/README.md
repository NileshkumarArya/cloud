# CWMS - Cloud Workload Management System

A lightweight, local, research-oriented prototype for observing synthetic cloud
workloads, distributing requests across simulated backend nodes, detecting
traffic surges, forecasting near-term demand, and comparing scheduling policies.

> **All workload, load, and latency values are simulated.** This project is not
> a production load balancer, does not provision cloud resources, and is not
> connected to Azure. See [Known limitations](#known-limitations).

## Project purpose

The prototype demonstrates, end to end:

1. Synthetic request generation (normal, burst, node-failure, and overload
   scenarios).
2. Health-aware request distribution using selectable scheduling policies.
3. Bounded per-node admission queues with explicit overload rejection and
   simulated request timeouts.
4. Per-node and system metrics collection, separated into accepted, completed,
   failed/timed-out, queued, and rejected counts.
5. Configurable rate, average-load, and maximum-node-load surge detection.
6. Causal moving-average and change-aware forecasting with MAE/RMSE
   comparisons against the moving-average and naive baselines.
7. Rule-based capacity recommendations.
8. CSV/JSON export and SQLite persistence of completed runs.
9. A web dashboard and REST API for running and inspecting simulations, with
   optional bearer auth, request-size/volume limits, and safe local defaults.
10. A repeatable five-seed experiment comparing four policies across four
    scenarios (80 runs).

## Architecture

```text
Traffic generator (synthetic)
        |
        v
Scheduler / distributor  <-- policy: round-robin | least-loaded | fcfs | adaptive
        |
        v
Admission control  <-- bounded per-node queue, overflow rejection, timeout
        |
        v
Simulated backend nodes (capacity, load, health)
        |
        v
Metrics collector
        |
        +--> Surge detector (rate, average, max node load)
        +--> Forecaster (causal moving average / change-aware)
        +--> Recommendation engine
        |
        v
FastAPI REST API + dashboard + CSV/JSON + SQLite history
```

The scheduling policy is separate from metrics, surge detection, forecasting,
recommendations, and persistence. Policy decisions are recorded per run.

### Policies

| Policy | Source | Behaviour |
|---|---|---|
| `round-robin` | Supplied documents | Next healthy node in sequence |
| `least-loaded` | Supplied documents | Healthy node with lowest current load; equal-load ties prefer fewer prior assignments |
| `fcfs` | Build brief extension | First healthy node in configuration order (baseline) |
| `adaptive` | Build brief extension | Least-loaded normally; capacity-first when the forecast exceeds remaining cluster headroom, with fair equal-headroom tie-breaking |

The supplied document pack specifies only round-robin and least-loaded. FCFS and
adaptive were added because the build brief asks for that comparison; they are
labelled as extensions and are not presented as documented requirements.

## Project layout

```text
code/
|-- cwms_simulator/        # Core simulation package
|   |-- nodes.py           # Node model and health
|   |-- policies.py        # Scheduling policies
|   |-- traffic_generator.py
|   |-- metrics.py
|   |-- surge_detector.py
|   |-- forecaster.py      # Causal moving-average and change-aware strategies
|   |-- recommendations.py
|   |-- simulator.py       # Orchestration + CSV/JSON export
|   |-- storage.py         # SQLite persistence
|   `-- cli.py             # Command-line interface
|-- cwms_api/              # FastAPI backend
|-- cwms_dashboard/        # HTML/CSS/JS dashboard
|-- cwms_tests/            # unittest suite (187 tests)
|-- cwms_scripts/          # Start/test/experiment/prune/browser-smoke scripts
|-- cwms_config/           # Default configuration reference
|-- cwms_data/             # Generated datasets and SQLite DB
|-- cwms_docs/             # Architecture, API, testing, Azure plan, traceability
|-- output/
|   |-- reports/           # Implementation, test, research, review, audit, packaging reports
|   `-- documentation-updates/
|-- run_simulator.py
|-- run_api.py
|-- requirements.txt
|-- requirements-dev.txt
`-- requirements-browser.txt
```

## Prerequisites

- Python 3.10+ (tested with 3.10.11 on Windows).
- Optional: Node.js only for `node --check` frontend syntax validation.
- No paid services, cloud account, Docker, or database server required.
- The dashboard loads Chart.js from a public CDN; offline use still works but
  charts are skipped with a warning.

## Installation

```powershell
cd "C:\projects\azure prototype\code"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Linux/macOS:

```bash
cd code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The simulator and its tests use only the Python standard library. FastAPI,
Uvicorn, and httpx are needed only for the API/dashboard and API tests.

## Run the command-line simulator

```powershell
python run_simulator.py
python run_simulator.py --policy round-robin
python run_simulator.py --policy adaptive --burst-rate 180 --fail-node backend-b
python run_simulator.py --intervals 10 --burst-start 4 --burst-end 8 --output cwms_data/demo.csv --json-output cwms_data/demo.json --quiet
python run_simulator.py --overload-threshold 80 --queue-limit 10 --request-timeout-ms 100
```

Useful options: `--policy {round-robin,least-loaded,fcfs,adaptive}`,
`--intervals`, `--base-rate`, `--burst-rate`, `--burst-start`, `--burst-end`,
`--surge-threshold`, `--load-threshold`, `--max-load-threshold`, `--fail-node`,
`--forecast-window`, `--forecast-strategy`, `--disable-admission-control`,
`--overload-threshold`, `--queue-limit`, `--request-timeout-ms`, `--seed`,
`--output`, `--json-output`, `--quiet`.

Admission control is enabled by default. A request below the node's
`overload_threshold` is accepted immediately; at or above it, the request waits
in a bounded per-node queue and is rejected as overload when that queue is full.
Queued requests whose estimated wait exceeds `request_timeout_ms` fail as
timeouts instead of being counted as completed.

Exit codes: `0` success, `2` invalid configuration.

## Run the API and dashboard

```powershell
python run_api.py
```

Then open:

- Dashboard: <http://127.0.0.1:8000/dashboard>
- API docs (Swagger): <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

Optional environment variables (see `.env.example`):

```powershell
$env:CWMS_API_HOST = "127.0.0.1"
$env:CWMS_API_PORT = "8000"
$env:CWMS_DB_PATH  = "cwms_data/cwms.db"
$env:CWMS_API_TOKEN = "replace-with-a-long-random-token"   # optional
$env:CWMS_CORS_ORIGINS = ""                                # opt-in allowlist
python run_api.py
```

The API does not auto-load `.env` files and contains no credentials. It binds to
`127.0.0.1` by default. When `CWMS_API_TOKEN` is set, state-changing POST
endpoints require `Authorization: Bearer <token>`; the dashboard shows a token
field and keeps the value in session storage only. Binding to a non-loopback
address without a token is refused unless
`CWMS_ALLOW_UNAUTHENTICATED_REMOTE=1` is explicitly set. CORS is disabled unless
`CWMS_CORS_ORIGINS` lists explicit origins. Request bodies are capped at 32 KiB
and a simulation is capped at 100,000 generated requests.

### Main API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/config` | Defaults and available policies/scenarios |
| POST | `/api/simulation/start` | Run a custom simulation |
| GET | `/api/simulation/status` | Current/final run status |
| GET | `/api/simulation/results` | Per-interval results |
| GET | `/api/simulation/summary` | Aggregated summary |
| POST | `/api/scenarios/run` | Run `normal`, `burst`, `failure`, or `overload` |
| GET | `/api/scenarios` | List scenarios |
| GET | `/api/nodes` | Node status |
| POST | `/api/nodes/{name}/health?healthy=true\|false` | Set node health; retained for later runs |
| GET | `/api/export/csv`, `/api/export/json` | Download the latest result |
| GET | `/api/history?limit=20` | Persisted runs, newest first |
| GET | `/api/history/{run_id}` | One persisted run with metrics |
| POST | `/api/history/prune` | Delete old runs, keeping the newest N (auth-protected) |
| GET | `/dashboard` | Web dashboard |

Full details and examples: [cwms_docs/API_REFERENCE.md](cwms_docs/API_REFERENCE.md).

## Database

SQLite is initialised automatically at `cwms_data/cwms.db` (override with
`CWMS_DB_PATH`). Tables:

- `runs` - timestamp, label, policy, config JSON, summary JSON.
- `interval_metrics` - per-interval accepted/completed/failed/timed-out/queued
  and rejection-reason counts, surge, forecast, recommendation.
- `node_metrics` - per-node assignment/completion/failure/queue/latency/load.

Foreign keys cascade from `runs`. Every completed API run is saved in one
transaction. The schema is versioned (currently v2) and existing v1 databases
are migrated in place by adding the new columns. History can be pruned with
`python cwms_scripts/prune_history.py --keep-latest 50` or
`POST /api/history/prune` when authenticated. Deleting the database file resets
history.

## Run tests

```powershell
python -m unittest discover -s cwms_tests -t . -v
```

or:

```powershell
powershell -File cwms_scripts/run_tests.ps1
```

Optional frontend syntax check:

```powershell
node --check cwms_dashboard/app.js
```

Optional headless browser smoke test (requires `requirements-browser.txt` and
Microsoft Edge):

```powershell
python -m pip install -r requirements-browser.txt
python cwms_scripts/browser_smoke.py
```

Test categories include node model and admission queues, policies, traffic
generation, metrics, rate/average/max-load surge detection, forecast strategies
and error metrics, recommendations, SQLite persistence and migration, end-to-end
simulator scenarios including overflow/timeouts, CSV/JSON exports, API
integration/validation/security, and static dashboard checks. Results:
[output/reports/TEST_REPORT.md](output/reports/TEST_REPORT.md).

## Run the experiment

```powershell
python cwms_scripts/run_experiment.py
```

This runs 4 scenarios x 4 policies x 5 seeds (80 runs) with identical inputs per
scenario/policy and writes:

- `cwms_data/experiment_results.csv` - raw per-seed results.
- `cwms_data/experiment_summary.csv` - mean and 95% confidence intervals per
  scenario/policy.
- `output/reports/experiment_raw_results.md`
- `output/reports/experiment_summary.md`

Interpretation and limitations: [output/reports/RESEARCH_EVALUATION_REPORT.md](output/reports/RESEARCH_EVALUATION_REPORT.md).

## Verified behaviour (summary)

- All 187 automated tests pass locally.
- Simulated burst scenario triggers surge events at the configured threshold.
- Maximum-node-load detection catches FCFS concentration that the average-load
  rule misses.
- Unhealthy nodes receive zero new assignments.
- Round-robin, least-loaded, FCFS, and adaptive all process the same generated
  workload for a given seed.
- Bounded queues reject overflow and timed-out requests are counted separately
  from completions; accounting identities hold over the 80-run experiment.
- Forecasts use only observations from earlier intervals; the selected strategy,
  pure moving average, and naive baseline are scored on the same intervals.
- CSV/JSON exports contain the documented fields.
- Runs persist in SQLite, survive a new store/API process, and v1 history
  migrates to the v2 schema.
- API and dashboard assets pass HTTP and headless-browser smoke tests.
- In the overload experiment, bounded admission turns excess load into explicit
  overflow/timeout outcomes instead of unbounded latency. Adaptive completed a
  mean of 745 of 931 accepted requests (80.0%) versus 687 of 983 (69.9%) for
  least-loaded, at the cost of 52 more rejections.

## Known limitations

- **Simulated metrics only.** Node load and response time are synthetic; no real
  CPU/RAM/disk telemetry is collected. The dashboard labels values as simulated.
- **Admission and queueing are simplified.** Queue wait is estimated from node
  capacity and queue position, not a discrete-event queue. A queue drains at the
  end of each interval, so requests never carry across intervals. Timeout
  behaviour is therefore illustrative rather than a production SLO model.
- **No Azure integration.** No cloud resource has been created or contacted.
- **Optional bearer auth only.** There are no user accounts, roles, audit trail,
  rate limiting, or TLS termination in the app. The safe default is localhost
  plus an optional shared token; it is not an internet-facing security boundary.
- **No autoscaling.** Recommendations are advisory text; nothing is provisioned.
- **Single active run**, held in memory; the run cannot be cancelled mid-flight.
  Completed runs are persisted.
- **Forecast is still a baseline.** The default change-aware strategy reduces
  burst MAE from 45.06 (pure moving average) to 18.56, close to the 19.09 naive
  last-value result; it still cannot anticipate the first burst interval or the
  burst end. It is not a machine-learning model.
- **Adaptive is not a general measured win.** After fair tie-breaking it is
  indistinguishable from least-loaded in failure and slightly slower in burst.
  In the artificial overload scenario it completed more accepted requests but
  rejected slightly more, so the result does not establish general superiority.
- **Charts require the Chart.js CDN**; tables remain usable offline.
- **Five seeds** provide a small repeatability check and 95% confidence
  intervals, not statistical significance.
- Not production-ready: no load testing, HA, distributed execution, or security
  certification.

## Azure (not performed)

No Azure resource was created, started, resized, or billed. For a future safe
integration plan see [cwms_docs/AZURE_INTEGRATION_PLAN.md](cwms_docs/AZURE_INTEGRATION_PLAN.md).
Any billable action requires explicit approval after checking current pricing and
subscription terms.

## Source documents

The original requirements pack is preserved unmodified outside this folder at
`CWMS_Updated_Company_Oriented_Document_Pack/...`. No original document was
edited. Document review and decision log:
[output/reports/DOCUMENT_REVIEW_REPORT.md](output/reports/DOCUMENT_REVIEW_REPORT.md).

