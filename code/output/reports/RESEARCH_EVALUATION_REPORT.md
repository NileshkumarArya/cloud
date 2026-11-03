# Research Evaluation Report

## 1. Purpose

Evaluate the implemented scheduling, admission, detection, forecasting, and
recommendation logic against the research questions in the supplied documents,
using only the local synthetic simulator. This is a reproducible engineering
evaluation, not a peer-reviewed study.

## 2. Research questions

Adapted from `08_Research_and_Limitations.md` and the build brief:

- **RQ1:** How do round-robin and least-loaded compare under normal and burst
  traffic?
- **RQ2:** Does health-aware routing help when a node fails?
- **RQ3:** How accurate are causal moving-average and change-aware forecasts
  compared with the causal naive baseline?
- **RQ4:** Are rule-based recommendations operationally meaningful?
- **RQ5 (extension):** How do FCFS and a forecast-aware adaptive policy compare
  with the documented policies?
- **RQ6 (extension):** What changes when bounded admission queues, overflow
  rejection, and simulated timeouts are enabled?

## 3. Method

| Item | Value |
|---|---|
| Scenarios | `normal`, `burst`, `failure`, `overload` |
| Policies | FCFS, round-robin, least-loaded, adaptive |
| Seeds | 7, 13, 29, 41, 53 |
| Intervals | 20 |
| Runs | 4 x 4 x 5 = 80 |
| Nodes | `backend-a` 100, `backend-b` 100, `backend-c` 75 |
| Normal | base 40 requests/interval |
| Burst | base 40, burst 180 on intervals 8-12 |
| Failure | base 50, `backend-b` unhealthy |
| Overload | base 120, threshold 80, queue 10, timeout 100 ms |
| Default admission | enabled, threshold 100, queue 50, timeout 2000 ms |
| Surge thresholds | 90 requests/interval; 80% average load; 100% maximum node load |
| Forecast | Default `change_aware`; pure 5-interval MA and naive last-value scored as comparators |
| Selection ties | Fewer prior assignments wins after load/headroom |
| Uncertainty | Two-sided 95% confidence intervals using Student's t with df=4 |

For each seed, every policy receives the same generated request sequence and the
same node configuration. This controls workload differences when comparing
policies. Metrics are synthetic.

### Metric definitions

- **Accepted:** immediate plus queued admissions. Rejected requests are not
  accepted.
- **Queued:** accepted requests that waited at or above the overload threshold.
- **Failed/timed out:** admitted requests whose estimated wait exceeded the
  timeout. In this build, timeout is the only failure reason.
- **Completion rate:** completed / accepted. **Acceptance rate:** accepted /
  generated. **Queue rate:** queued / accepted.
- **Peak load:** highest maximum node load in any interval (cap 150%).
- **Final load spread:** max minus min load among healthy nodes at the end.
- **Mean simulated latency:** total simulated latency / completed requests.
- **Forecast errors:** MAE/RMSE over intervals that had prior history; the first
  interval is excluded because no causal forecast is possible.
- **Surge events:** alerts raised after cooldown suppression. These are rule
  firings, not precision/recall against labelled incidents.

## 4. Results

Mean over five seeds. Confidence intervals are shown for latency and selected
forecast MAE.

| Scenario | Policy | Accepted | Rejected | Queued | Completed | Failed | Peak load | Spread | Latency ms (95% CI) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| normal | FCFS | 783.8 | 0.0 | 629.4 | 783.8 | 0.0 | 150.0 | 150.0 | 183.18 (179.98-186.38) |
| normal | round-robin | 783.8 | 0.0 | 54.6 | 783.8 | 0.0 | 121.76 | 28.54 | 40.49 (39.59-41.39) |
| normal | least-loaded | 783.8 | 0.0 | 0.0 | 783.8 | 0.0 | 100.5 | 2.58 | 37.02 (36.74-37.30) |
| normal | adaptive | 783.8 | 0.0 | 0.0 | 783.8 | 0.0 | 100.5 | 2.58 | 37.02 (36.74-37.30) |
| burst | FCFS | 868.4 | 610.2 | 714.0 | 868.4 | 0.0 | 150.0 | 150.0 | 211.02 (210.17-211.87) |
| burst | round-robin | 1431.4 | 47.2 | 793.4 | 1431.4 | 0.0 | 150.0 | 28.93 | 190.94 (187.58-194.30) |
| burst | least-loaded | 1381.2 | 97.4 | 712.4 | 1381.2 | 0.0 | 150.0 | 2.56 | 183.11 (182.55-183.67) |
| burst | adaptive | 1381.2 | 97.4 | 711.6 | 1381.2 | 0.0 | 150.0 | 2.51 | 183.22 (182.61-183.83) |
| failure | FCFS | 983.4 | 0.0 | 834.6 | 983.4 | 0.0 | 150.0 | 150.0 | 233.89 (229.64-238.14) |
| failure | round-robin | 983.4 | 0.0 | 692.6 | 983.4 | 0.0 | 150.0 | 0.00 | 136.02 (133.29-138.75) |
| failure | least-loaded | 983.4 | 0.0 | 697.6 | 983.4 | 0.0 | 150.0 | 0.00 | 137.15 (134.68-139.62) |
| failure | adaptive | 983.4 | 0.0 | 692.8 | 983.4 | 0.0 | 150.0 | 0.00 | 136.29 (133.54-139.04) |
| overload | FCFS | 356.0 | 2016.6 | 200.0 | 256.0 | 100.0 | 112.95 | 112.78 | 48.71 (48.71-48.71) |
| overload | round-robin | 1004.0 | 1368.6 | 600.0 | 664.0 | 340.0 | 123.71 | 10.93 | 51.58 (51.58-51.58) |
| overload | least-loaded | 983.0 | 1389.6 | 556.0 | 687.0 | 296.0 | 114.96 | 2.04 | 51.13 (51.13-51.13) |
| overload | adaptive | 931.0 | 1441.6 | 446.0 | 745.0 | 186.0 | 123.97 | 23.11 | 48.86 (48.86-48.86) |

Admission rates:

| Scenario | Policy | Acceptance % | Completion % | Queue % | Timeout % |
|---|---|---:|---:|---:|---:|
| normal | FCFS / RR / LL / adaptive | 100 / 100 / 100 / 100 | 100 / 100 / 100 / 100 | 80.30 / 6.96 / 0.00 / 0.00 | 0 / 0 / 0 / 0 |
| burst | FCFS / RR / LL / adaptive | 58.76 / 96.84 / 93.46 / 93.46 | 100 / 100 / 100 / 100 | 82.22 / 55.42 / 51.58 / 51.52 | 0 / 0 / 0 / 0 |
| failure | FCFS / RR / LL / adaptive | 100 / 100 / 100 / 100 | 100 / 100 / 100 / 100 | 84.87 / 70.42 / 70.93 / 70.44 | 0 / 0 / 0 / 0 |
| overload | FCFS / RR / LL / adaptive | 15.01 / 42.32 / 41.44 / 39.24 | 71.91 / 66.14 / 69.89 / 80.02 | 56.18 / 59.76 / 56.56 / 47.91 | 28.09 / 33.86 / 30.11 / 19.98 |

Forecast comparison by scenario:

| Scenario | Selected MAE | Pure MA MAE | Naive MAE | Selected RMSE | Pure MA RMSE | Naive RMSE |
|---|---:|---:|---:|---:|---:|---:|
| normal | 1.87 | 1.87 | 2.46 | 2.24 | 2.24 | 2.94 |
| failure | 2.45 | 2.45 | 3.23 | 2.90 | 2.90 | 3.85 |
| burst | 18.56 | 45.06 | 19.09 | 45.73 | 66.94 | 46.89 |
| overload | 5.81 | 5.81 | 7.67 | 6.90 | 6.90 | 9.12 |

Forecast errors are identical across policies within a scenario because each
seed feeds the same request sequence. Selected and pure-MA errors are identical
on non-burst traffic because the change-aware rule falls back to the moving
average when the recent spread is stable.

Raw data: `cwms_data/experiment_results.csv`. Summary:
`cwms_data/experiment_summary.csv`. Generated tables:
`experiment_raw_results.md`, `experiment_summary.md`.

## 5. Analysis

### RQ1 - Round-robin versus least-loaded

Least-loaded kept the best balance and latency in normal traffic:

- Normal peak load: 100.5% versus 121.76% for round-robin.
- Normal final spread: 2.58 versus 28.54 percentage points.
- Normal mean latency: 37.02 ms versus 40.49 ms, with non-overlapping confidence
  intervals in this sample.
- Normal queue rate: 0% versus 6.96%. Admission control starts queueing earlier
  on round-robin because it keeps pushing work at a loaded node.

Under burst traffic both policies hit the load cap. Least-loaded accepted 1381
of 1479 requests (93.5%) versus 1431 (96.8%) for round-robin, while keeping a
much smaller final spread (2.56 vs 28.93) and lower latency (183.11 vs 190.94
ms). Round-robin accepted more but queued more and ended less balanced. This is
a trade-off between admission volume and balance, not a universal win.

### RQ2 - Health-aware routing under failure

All policies skipped the failed node. Because the two remaining nodes still had
queue capacity, every generated request was accepted and completed:

- FCFS: 983.4 accepted, 0 rejected, 233.89 ms.
- Round-robin: 983.4 accepted, 0 rejected, 136.02 ms.
- Least-loaded: 983.4 accepted, 0 rejected, 137.15 ms.
- Adaptive: 983.4 accepted, 0 rejected, 136.29 ms.

FCFS's higher latency comes from concentrating work on `backend-a`; its queue
rate is 84.9% versus about 70% for the load-aware policies. Acceptance is not a
useful resilience discriminator in this scenario because two nodes still exceed
demand. A harsher failure/overload combination would be needed to show rejection
differences.

### RQ3 - Forecast accuracy

The change-aware strategy closes most of the moving-average lag at burst onset:

- Burst selected MAE 18.56 versus 45.06 for pure MA and 19.09 for naive.
- Burst selected RMSE 45.73 versus 66.94 for pure MA and 46.89 for naive.
- Normal selected/MA MAE 1.87 versus 2.46 for naive.
- Failure selected/MA MAE 2.45 versus 3.23 for naive.
- Overload selected/MA MAE 5.81 versus 7.67 for naive.

The selected burst MAE is only marginally better than naive and its 95% interval
is wide (+/-1.81), so this is not a claim of material superiority. Change-aware
cannot anticipate the first interval of a burst or the return to normal; it
reacts after the first changed observation. It remains a transparent rule, not a
machine-learning model.

### RQ4 - Rule-based recommendations

Recommendations fired for overload, surge, imbalance, node failure, and sustained
low load, and were recorded per interval and in summaries. They are transparent
and testable. However, this evaluation did **not** measure whether an operator
would act correctly on them, nor any outcome improvement from following them.
Their operational value is therefore plausible but unvalidated.

### RQ5 - FCFS and adaptive extensions

- **FCFS** concentrated all traffic on `backend-a`. In normal traffic it still
  completed everything, but 80.3% of accepted requests waited and mean latency was
  183.18 ms versus 37.02 ms for least-loaded. In burst it was rejected heavily
  (610 of 1478 requests) because its queue filled. It is a useful stress baseline,
  not a viable strategy.
- **Adaptive** matched least-loaded exactly in normal traffic because the forecast
  never exceeded remaining headroom. In burst it was almost identical (183.22 vs
  183.11 ms) with a marginally lower spread (2.51 vs 2.56).
- In failure it was indistinguishable from round-robin/least-loaded on acceptance
  and balance, with essentially the same latency.
- In the artificial overload scenario adaptive completed 745 of 931 accepted
  requests (80.0%) versus 687 of 983 (69.9%) for least-loaded, but rejected 52
  more requests overall. It spread work more evenly (queue rate 47.9% vs 56.6%)
  and reduced timeouts, at the cost of lower acceptance. This is a single
  scenario and does not establish general superiority.

### RQ6 - Bounded admission, overflow, and timeouts

The overload scenario shows the intended qualitative change:

- Without a bound, excess demand would inflate load/latency indefinitely. With
  `queue_limit=10`, each node accepts at most 10 waiting requests per interval;
  the rest are explicit `overload` rejections.
- FCFS accepted only 15.0% of generated requests and timed out 100 of 356
  accepted requests.
- Round-robin and least-loaded accepted about 41-42% and timed out 30-34% of
  accepted requests.
- Adaptive accepted 39.2% but completed 80.0% of accepted requests, the best
  completion rate, because its distribution kept queue positions shorter.
- All policies recorded `rejected_no_capacity = 0`: every rejection in this
  scenario came from a full queue, not from a missing healthy node. Across all
  80 runs, generated = accepted + rejected and accepted = completed + failed.

The latency results in overload are nearly deterministic across seeds because
the queue drain uses node capacity and queue position rather than random service
times. Confidence intervals of zero therefore reflect the model, not evidence of
extreme precision.

## 6. Surge detection

The original average-load rule could miss a single saturated node: FCFS reached
150% peak load while the cluster average remained low. The detector now also
checks the average of each interval's *maximum* node load against a 100%
threshold, with priority `rate > max_load > average_load` and a two-interval
cooldown. FCFS normal runs record 9 surge events.

This closes the known blind spot, but the experiment measures rule firings, not
detection precision or recall. There is no labelled incident set, and a threshold
at nominal capacity may be noisy for policies that legitimately hover near 100%.
Threshold sensitivity remains future work.

## 7. Validity and limitations

- **Internal validity:** good for policy comparison because workload, seeds, and
  configuration are controlled; the experiment is reproducible.
- **Construct validity:** load and latency are simplified formulas. Queue wait is
  estimated from capacity and position; it is not a discrete-event queue and
  drains once per interval. "Latency" is a synthetic cost index.
- **External validity:** weak. One topology, one capacity mix, five seeds, 20
  intervals, no real traffic or cloud behavior.
- **Statistical validity:** 95% confidence intervals describe seed variability;
  no hypothesis test or power analysis was performed, and five seeds are not
  enough for broad significance claims.
- **Metric limits:** the 150% load cap truncates severity; final spread captures
  only the end state; timeout is driven by an approximate wait formula.
- **Recommendation validity:** rules were not evaluated against human decisions or
  downstream outcomes.
- **Forecast validity:** the scoring window excludes the first interval; all
  forecast strategies use the same scored intervals. Change-aware is evaluated
  in-sample as a fixed rule, not tuned per scenario.

## 8. Recommendations for future work

1. Replace the per-interval queue approximation with a discrete-event queue or a
   real service-time distribution, and validate timeout/rejection behavior.
2. Run threshold sensitivity analysis for rate, average-load, and maximum-load
   detection, and add labelled incidents to measure precision/recall.
3. Increase seeds and use hypothesis tests or mixed-effects models; add
   sensitivity analysis for capacities, burst magnitude, queue limits, and
   timeouts.
4. Test harsher failure/overload combinations where remaining capacity cannot
   absorb demand, so resilience differences become observable.
