# Geatpy integration validation

Validation date: 27 September 2026.

## Reproducible environment

The real Geatpy integration is validated in a pinned Linux amd64 container because Geatpy 2.7.0 does not publish a macOS ARM wheel. The environment contains:

- pinned `python:3.10-slim` base-image digest (resolved to Python 3.10.21/x86-64 in the verified build);
- the official Geatpy 2.7.0 CPython 3.10 manylinux x86-64 wheel and its SHA-256 fragment;
- NumPy 1.26.4 and Matplotlib 3.8.4;
- Debian `libgomp1`, required by the wheel's compiled modules;
- `MPLBACKEND=Agg`, `PYTHONDONTWRITEBYTECODE=1` and `REQUIRE_GEATPY=1`.

The repository is mounted read-only into the runtime container. No fallback implementation is labelled as Geatpy.

## Run

On a machine with Docker:

```bash
sh tools/run_geatpy_tests.sh
```

The script builds [`Dockerfile.geatpy`](../Dockerfile.geatpy), runs the separate [`integration_geatpy.py`](../tests/integration_geatpy.py) real-library suite and then executes the Geatpy CLI solver on the synthetic fixture. On Apple Silicon, Docker uses Linux amd64 emulation because the official wheel is x86-64 only. The platform-independent default discovery therefore reports 66 core tests with no skipped Geatpy cases; the container supplies the other 12 mandatory tests.

## Verified result

The first clean-container attempt established that the Python wheel installs but requires `libgomp.so.1`. After declaring `libgomp1`, all 12 integration tests passed; the final suite includes graph-heuristic population seeding:

- exact-baseline agreement across seeds;
- adaptive/catastrophe flag independence;
- restart and seed reproducibility;
- candidate evaluation accounting;
- infeasible, disconnected and single-edge cases;
- hard-deadline route choice;
- Geatpy population objective/constraint array shapes;
- invalid search-budget rejection.
- graph-heuristic seed insertion and preservation.

The larger result experiment and its figures are documented in [`GEATPY_RESULTS_ANALYSIS_CN.md`](GEATPY_RESULTS_ANALYSIS_CN.md).

This validates the maintained Geatpy integration in the stated container. It does not reproduce the unknown 2022 random state or turn heuristic results into global-optimality certificates.
