# Allocation control tuning

This directory records mechanism and hyperparameter selection on synthetic-search seeds 30--39, separate from the formal 0--29 report and held-out 40--69 validation.

- `runs.csv`: 12 configurations × 10 seeds.
- `summary.csv`: feasible-run distribution summaries.
- `results.json`: configuration definitions, predeclared selection rule and best observed solution.

The selected configuration is `v2-r25-p30-m3`: diversity/stagnation control, a 1.25--2.75 effective expected-mutation range under a 3.0 hard cap, 30-generation patience and 25% partial restart. Selection used lowest median, then mean, then best feasible cost. These are synthetic-instance results, not carrier operations or a global-optimality claim.

Reproduce with:

```bash
python3 -B tools/tune_allocation_control.py
```
