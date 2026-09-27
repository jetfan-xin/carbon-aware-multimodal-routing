# Held-out allocation control validation

This directory validates the selected controller on synthetic-search seeds 40--69, which were not used for configuration selection.

- `runs.csv`: five configurations × 30 paired seeds.
- `summary.csv`: feasible-run distribution summaries and controller diagnostics.
- `results.json`: summaries, paired differences and best observed solution.

All 150 runs use 100 individuals × 150 generations and find feasible solutions. The approximate 95% intervals describe paired seed-level differences on one fixed synthetic instance; they do not establish performance on other networks or real operations.

Reproduce with:

```bash
python3 -B tools/validate_allocation_control.py
```
