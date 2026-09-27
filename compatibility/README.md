# Compatibility boundary

`run_original.py` redirects the recovered Windows workbook paths to user-supplied directories and runs the byte-exact `historical/GA_code/main.py`. It does not edit the snapshot or replace Geatpy's operators.

The wrapper is deliberately guarded because the original entry point evaluates 100,000 candidates, prints two lines per candidate, opens plots and writes Geatpy result files. Run it only in a disposable output directory and use `python -B` to avoid creating bytecode next to the snapshot.

This layer does not make the project fully reproducible. The exact 2022 Python/dependency versions and random state are unknown, and Geatpy 2.7.0 native binaries are platform-specific.
