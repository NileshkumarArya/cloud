# Packaging Report

## 1. Artifact

| Item | Value |
|---|---|
| Archive | `code/output/CWMS_Complete_Project.zip` |
| Internal root | `CWMS_Complete_Project/` |
| Format | ZIP, deflate |
| Contents | Source, tests, docs, config, experiment data, reports |
| Self-inclusion | Archive excludes itself |
| External originals | Supplied document pack and ZIP untouched |

The final archive size and SHA-256 are recorded in the delivery message after the
last rebuild, because embedding a hash inside the archive would change the hash.

## 2. Included content

| Area | Files | Notes |
|---|---:|---|
| Root | 8 | README, requirements, launchers, `.env.example`, `.gitignore` |
| `cwms_simulator/` | 12 | Core simulation package incl. admission/queue/timeout logic |
| `cwms_api/` | 3 | FastAPI application with optional auth and limits |
| `cwms_dashboard/` | 3 | HTML, CSS, JS |
| `cwms_tests/` | 12 | 187 unittest tests |
| `cwms_scripts/` | 9 | Experiment, browser-smoke, prune, start/test scripts (PS1 + SH) |
| `cwms_config/` | 1 | Default configuration reference |
| `cwms_docs/` | 6 | Architecture, API, testing, security, Azure plan, traceability |
| `cwms_data/` | 3 | Raw/summary experiment CSVs and data README |
| `output/reports/` | 8 | Five required reports + audit + two experiment tables |
| `output/documentation-updates/` | 1 | Proposed document changes |
| **Total** | **66** | Includes this report and `AUDIT_REPORT.md` |

## 3. Excluded content and rationale

| Excluded | Reason |
|---|---|
| `__pycache__/`, `*.pyc`, `.pytest_cache/` | Generated build artifacts |
| `.venv/`, `venv/` | Environment-specific and reproducible |
| `*.db`, `*.db-wal`, `*.db-shm`, `*.db-journal` | Runtime history; created automatically |
| `*.log` | Environment-specific smoke/test logs |
| `results/` | Runtime CLI/API export directory |
| `sim_*.csv`, `demo_*.csv/json` | Redundant generated per-run exports |
| `CWMS_Complete_Project.zip` | Prevents self-nesting |
| Secrets/credentials | None exist; `.env.example` uses placeholders only |

## 4. Verification performed

1. **Archive integrity:** `ZipFile.testzip()` returned `None` (no corrupt entry).
2. **Inventory:** 66 files under a single `CWMS_Complete_Project/` root; no nested
   ZIP.
3. **Fresh extraction:** extracted to a temporary directory outside the workspace.
4. **Tests from extracted copy:** `python -m unittest discover -s cwms_tests -t .`
   run in the extracted root.
5. **Syntax:** `node --check cwms_dashboard/app.js` in the extracted copy.
6. **No runtime state:** no database, WAL/SHM sidecars, logs, caches, virtual
   environment, `results/`, or generated per-run CSV files are present.
7. **Browser smoke:** `python cwms_scripts/browser_smoke.py` passed with the
   normal and overload scenarios.
8. **Secret scan:** no real tokens or credentials; only placeholder `.env.example`
   values and test literals.

## 5. Verification results

| Check | Result |
|---|---|
| ZIP integrity | Pass (`testzip=None`) |
| Entry count | 66 files |
| Required reports present | Yes (5/5 + audit + experiment tables) |
| API/simulator/dashboard/tests present | Yes |
| Extracted test suite | 187 tests, OK |
| Extracted JS syntax | OK |
| Browser smoke | Pass (Edge, 20 rows; overload and timeout counts visible) |
| Nested archive | None |
| Runtime DB/results included | No |
| Secrets | None |

## 6. Reproduce from the archive

```powershell
Expand-Archive output\CWMS_Complete_Project.zip -DestinationPath .
cd CWMS_Complete_Project
python -m pip install -r requirements-dev.txt
python -m unittest discover -s cwms_tests -t . -v
python run_api.py
```

Dashboard: <http://127.0.0.1:8000/dashboard>

## 7. Notes

- The archive is self-contained for local simulation; only FastAPI/httpx need
  installation for the API and API tests.
- Chart.js is loaded from a CDN; offline use degrades to tables with a warning.
- No Azure credentials or resource identifiers are included.
- The archive is a snapshot; generated history is intentionally not shipped.
- Admission and timeout behavior are simplified local extensions, not production
  queueing or SLO claims.
