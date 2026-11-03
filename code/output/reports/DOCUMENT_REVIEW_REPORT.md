# Document Review Report

## 1. Scope and method

Reviewed the supplied pack in
`CWMS_Updated_Company_Oriented_Document_Pack/CWMS_Updated_Company_Ready_Pack/`:

- `docs/01_Project_Overview.md`
- `docs/02_PRD_Requirements.md`
- `docs/03_System_Architecture.md`
- `docs/04_Module_Design.md`
- `docs/05_Implementation_Roadmap.md`
- `docs/06_Test_Plan.md`
- `docs/07_Azure_Cost_Safety.md`
- `docs/08_Research_and_Limitations.md`
- `docs/09_College_Report.md`
- `docs/10_Presentation_Speaker_Notes.md`
- `prototype/simulator.py` and `prototype/README.md`

Each requirement was mapped to implementation or recorded as a gap. The original
files and the supplied ZIP were **not modified**; this review is read-only.

## 2. Summary of documented intent

- Local, low-cost prototype for cloud workload monitoring and decision support.
- Synthetic traffic across simulated backend nodes.
- Round-robin and least-loaded distribution.
- Per-node metrics, surge detection, moving-average forecast, rule-based
  recommendations, CSV output.
- Repeatable normal, burst, and failure scenarios.
- Clearly distinguish simulated values from real telemetry.
- Azure only as a later, cost-reviewed option; no provisioning without pricing and
  approval.
- No autoscaling, production SLA, or real cloud claims.

## 3. Alignment matrix

| Document intent | Implementation | Status |
|---|---|---|
| Synthetic workload generation | `TrafficGenerator` with seeded variation | Aligned |
| Round-robin | `RoundRobinPolicy` | Aligned |
| Least-loaded | `LeastLoadedPolicy` | Aligned |
| Health-aware routing | Policies skip unhealthy nodes | Aligned |
| Per-node/system metrics | `MetricsCollector` | Aligned (simulated) |
| Surge detection and alerts | `SurgeDetector` | Aligned; max-load rule added as extension |
| Moving-average forecast | `WorkloadForecaster` | Aligned; change-aware strategy added |
| MAE/RMSE evaluation | Selected, moving-average, and naive metrics computed and exported | Aligned |
| Rule-based recommendations | `RecommendationEngine` | Aligned |
| CSV output | Simulator/API export | Aligned |
| Normal/burst/failure/overload scenarios | Simulator, CLI, API, experiment | Aligned; overload is an extension |
| Label simulated data | Dashboard badge, README, reports, console note | Aligned |
| Repeatable tests | 187 stdlib tests | Aligned |
| Local/no paid cloud | No cloud calls or credentials | Aligned |
| Azure cost-first plan | Plan only, explicitly not executed | Aligned |
| No autoscaling claims | Recommendations are advisory only | Aligned |

## 4. Deliberate extensions beyond the documents

| Extension | Reason | Disclosure |
|---|---|---|
| FCFS policy | Build brief asks for comparison; useful baseline | Code docstring, README, reports |
| Adaptive policy | Build brief asks for adaptive scheduling | Code docstring, README, reports |
| FastAPI REST API | Build brief requires API | README/API reference |
| Web dashboard | Build brief requires UI; docs treat it as later work | README, dashboard "SIMULATED" badge |
| SQLite history | Not specified; adds persistence | README/architecture |
| Multi-seed experiment | Strengthens comparison | Research report |
| Bounded admission/queues/timeouts | Build-brief overload realism | README, architecture, API, security notes |
| Optional bearer auth/security limits | Safe local operation | README, SECURITY.md |

## 5. Ambiguities and decisions

1. **Which policies are required?** Documents name round-robin and least-loaded;
   the build brief adds FCFS/adaptive. Implemented all four, with the documented
   pair as the baseline and the others labeled extensions.
2. **Load-surge definition.** The module design explicitly says "average node
   load", so the average rule remains. The implementation adds a maximum-node-load
   rule as an extension because the average missed FCFS concentration (150% peak,
   zero alerts). Priority is rate, max load, then average load. On normal traffic,
   FCFS now records 9 events.
3. **Forecast baseline.** The documents ask for comparison with a naive baseline.
   The simulator computes selected, pure-MA, and causal last-value MAE/RMSE on the
   same scored intervals. On burst traffic change-aware scores 18.56 MAE, pure MA
   45.06, and naive 19.09; the small edge over naive is reported, not overstated.
4. **Dashboard timing.** The overview describes a dashboard as future work; the
   build brief requires one now. Implemented, with no production claims.
5. **Persistence.** CSV is required; a database is not specified. SQLite was added
   as a local, dependency-free extension for run history.
6. **Latency/load model.** Exact constants are unspecified. Implemented constants
   (load decay 0.55, 3.0 load points per normalized request, 20 ms base, 150% cap)
   are illustrative and now documented, but not validated against real systems.
7. **Admission control.** The source model focuses on routing and did not specify
   queues. A bounded admission extension was added: requests above the overload
   threshold wait, full queues reject as overload, and long waits time out. This
   is a simplified per-interval model, not a production queueing engine.
8. **Testing framework.** The pack does not mandate pytest; stdlib `unittest` was
   used because pytest was not installed. Tests remain reproducible.

## 6. Documentation inconsistencies / risks

- Speaker notes may imply a broader production system; the actual deliverable is a
  local simulation and must be described that way.
- The original prototype prints recommendations but does not implement the full
  architecture; our implementation extends it. Reports should not imply the
  original prototype already had these features.
- The cost-safety document correctly treats budget alerts as notifications; no
  report should describe them as hard caps.
- Any claim of "real cloud monitoring", "autoscaling", or "zero downtime" would
  contradict both the documents and the implementation.
- The docs' test plan does not include a browser E2E or load test; an optional
  single-browser Edge smoke test was added, while cross-browser and load testing
  remain not run.

## 7. Recommended updates to the documents (not applied)

1. Add a short "implemented extensions" section covering FCFS, adaptive, API,
   dashboard, and SQLite, clearly separated from original requirements.
2. Define surge detection precisely, including average and maximum node load;
   maximum-load detection now covers the former FCFS blind spot.
3. Replace "dashboard future work" with the current dashboard scope, or label the
   delivered dashboard as an extension.
4. Document simulation constants and the simplified admission/queue model.
5. Add the actual test command, test count, and environment versions.
6. Add the experiment design (4 scenarios x 4 policies x 5 seeds, 80 runs,
   95% confidence intervals) and updated results, with explicit non-significance
   caveats.
7. Update viva/speaker notes to include: no Azure resource created, synthetic
   latency, max-load detection, bounded admission/timeouts, and the absence of a
   general measured adaptive advantage.
8. Add a packaging/reproduction section pointing to README and scripts.
9. Clarify that MAE/RMSE are identical across policies for a scenario by design,
   because workload is held constant per seed.

A ready-to-use change note is in
`output/documentation-updates/documentation-updates.md`.

## 8. Preservation statement

No file in the supplied document pack or its ZIP was edited, moved, or deleted.
All implementation, generated data, reports, and packaging are inside `code/`.
