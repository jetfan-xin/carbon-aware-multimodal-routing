# Allocation control tuning

This directory records mechanism and hyperparameter selection on synthetic-search seeds 30--39, separate from the formal 0--29 report and held-out 40--69 validation.

- `runs.csv`: 12 configurations × 10 seeds.
- `summary.csv`: feasible-run distribution summaries.
- `results.json`: configuration definitions, predeclared selection rule and best observed solution.

The selected configuration is `v2-hybrid-archive-r25`: diversity/stagnation control, a 1.0--2.5 expected-mutation range under a 2.5 hard cap, 30-generation patience, 25% partial restart and an external opportunity-loss incumbent archive. Selection used lowest median, then mean, then best feasible cost. These are synthetic-instance results, not carrier operations or a global-optimality claim.

Reproduce with:

```bash
python3 -B tools/tune_allocation_control.py
```
