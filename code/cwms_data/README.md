# Generated Data

All values in this folder are produced by the local simulator and are synthetic.
They are not measurements from real servers or Azure.

## Included

| File | Description |
|---|---|
| `experiment_results.csv` | Raw results for 80 runs: 4 scenarios x 4 policies x seeds 7, 13, 29, 41, 53 |
| `experiment_summary.csv` | Mean metrics and t-based 95% confidence intervals per scenario/policy |

Regenerate with:

```powershell
python cwms_scripts/run_experiment.py
```

This also refreshes the Markdown tables in `../output/reports/`.

## Not included

Per-run `sim_*.csv`, demo exports, logs, and `cwms.db` are intentionally excluded
from the packaged project. They are recreated on demand by the simulator, API, and
tests. The SQLite database is created automatically at `cwms_data/cwms.db`
(override with `CWMS_DB_PATH`); delete it to reset run history.
