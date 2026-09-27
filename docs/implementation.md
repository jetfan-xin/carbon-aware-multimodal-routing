# Recovered implementation and execution boundary

## Repository roles

The primary historical implementation is the byte-exact snapshot in [`historical/GA_code`](../historical/GA_code). Its six Python files were recovered from the project archive and are dated 23 November 2022. They retain their original names, CRLF line endings, Windows paths, comments and defects.

The [`routing`](../routing) package is the actively maintained implementation. It supports controlled demonstrations and expanded validation, but it remains separate from the byte-exact 2022 source and does not redefine historical behavior.

## Historical call graph

```text
main.py
  -> ga.MyProblem
       -> input.py -> seven XLSX workbooks
       -> utils.py -> city IDs and transfer/mode helpers
       -> calculate.py -> transport, transfer, time and carbon cost
  -> Geatpy 2.7.0 SEGA template -> printed trace, plots and result directory

map.py -> coordinate workbook -> hard-coded Folium route HTML
       (no import or data flow from the optimizer)
```

`MyProblem` builds a 69-node, three-layer graph from 23 cities, greedily decodes a 69-integer priority vector and minimizes one scalar: transport + transfer + time-window + carbon cost. The retained entry configuration requests 100,000 individuals and one generation, but these are mutable experiment values. Geatpy's SEGA class contains the complete selection, crossover, mutation and elite parent-offspring loop. Separate 2022 logs and the defense trace confirm 100-generation historical runs; the surviving default must not be generalized into a claim that the algorithm was incomplete.

## Historical dependencies

The import-derived inventory is in [`historical/requirements-unpinned.txt`](../historical/requirements-unpinned.txt). Only Geatpy 2.7.0 is version-identifiable from the adjacent framework archive. NumPy, Pandas, an Excel engine, Folium and Matplotlib versions are unknown. The recovered native Geatpy modules target Windows/Linux x86-64 and CPython 3.6, not the current macOS ARM64/Python 3.13 environment. See [`historical/DEPENDENCIES.md`](../historical/DEPENDENCIES.md).

## Guarded compatibility runner

[`compatibility/run_original.py`](../compatibility/run_original.py) redirects only the original workbook reads and runs the unchanged entry point in a caller-selected output directory. It requires Geatpy 2.7.0, validates the seven workbook names, and refuses to run without acknowledgement because the original code prints 100,000 objective evaluations and writes plots/results.

```bash
python -B compatibility/run_original.py \
  --distance-dir /authorized/copy/distance \
  --parameter-dir /authorized/copy/parameters \
  --output-dir /tmp/ga-output \
  --acknowledge-large-run
```

Do not point it at the evidence source. Use copied data and a disposable output directory. Supplying `--seed` is a compatibility override and must not be described as an original setting.

## Verification performed

- All seven recovered files are protected by SHA-256 tests and [`historical/FILE_MANIFEST.json`](../historical/FILE_MANIFEST.json).
- The six Python files parse under Python 3.13.
- Copied workbooks loaded with a temporary isolated NumPy/Pandas/openpyxl environment.
- A minimal `ea.Problem` test double allowed construction and direct invocation without pretending to run Geatpy's genetic operators.
- Unchanged cost functions reproduce the displayed combined case as 9,618.65 transport + 500 transfer + 0 time + 154.045 carbon = 10,272.695 CNY, 61.2667 hours and 3,080.9 kg.
- The transfer-cost double count and the second-carbon-bracket `IndexError` are preserved and tested.

The full Geatpy run has not yet been reproduced byte-for-byte on the current machine: the exact 2022 environment and seed are unknown, and the available native framework modules are incompatible with the current platform. This current-platform limitation does not negate the preserved 2022 multi-generation logs and trace plot.

## Current maintained implementation

To run only the explicitly later model:

```bash
python3 -B -m routing \
  examples/synthetic-network.json --solver exact
```

The maintained implementation also provides a dependency-free equal-budget GA, state-Dijkstra baseline, order consolidation, capacity/edge-state handling, calibrated synthetic scale data and computed SVG maps. Its formulas and engineering safeguards are documented in [`current-implementation.md`](current-implementation.md) and are not backdated as exact historical behavior.

The optional compiled Geatpy path is verified on macOS ARM through [`Dockerfile.geatpy`](../Dockerfile.geatpy), which supplies a pinned Linux amd64/Python 3.10 environment, the official wheel and `libgomp1`. The 12 real-library integration tests pass there; details are recorded in [`GEATPY_VALIDATION.md`](GEATPY_VALIDATION.md). A 150-run ablation with generated SVG figures is analyzed in [`geatpy-results.md`](geatpy-results.md).
