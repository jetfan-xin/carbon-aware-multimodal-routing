# Current maintained implementation and validation

## Status and scope

This tested implementation uses explicit, auditable assumptions alongside the byte-exact historical snapshot. It is the actively maintained solver and remains distinct from the recovered 2022 implementation. See [source recovery](source-recovery.md) and the [comparison report](ORIGINAL_VS_CURRENT_CN.md).

The extension now covers individual route evaluation plus reproducible synthetic-order generation, greedy order consolidation, capacity checks, simulated edge closures, batch routing and computed SVG maps. It still does not claim production timetables, live APIs, blockchain services or a web platform.

## Implementation map

| File | Responsibility |
| --- | --- |
| [model.py](../routing/model.py) | Input validation, directed graph, historical rate bands, priority decoding, cost model, exact and state-Dijkstra baselines |
| [geatpy_solver.py](../routing/geatpy_solver.py) | Real Geatpy Problem/SEGA integration, operator adaptation and restarts |
| [native_ga.py](../routing/native_ga.py) | Dependency-free equal-budget baseline/adaptive/catastrophe ablations |
| [pipeline.py](../routing/pipeline.py) | Order validation/consolidation, closures, batch planning and SVG route maps |
| [synthetic.py](../routing/synthetic.py) | Explicitly labelled 23-city and larger synthetic benchmark generation |
| [CLI](../routing/__main__.py) | JSON input, solver selection, reproducible JSON output and input hash |
| [Synthetic example](../examples/synthetic-network.json) | Five-city test fixture with a dead end, a cycle and parallel transport modes |
| [Core tests](../tests/test_routing.py) | Hand-calculated costs, boundaries, scenarios, graph validation and exact checks |
| [Integration tests](../tests/integration_geatpy.py) | Real Geatpy runs, multiple seeds, restarts, constraints and baseline comparison |

## Model inputs and assumptions

The [parameter snapshot](../data/parameter_snapshot.json) supplies mode speeds, three candidate rates per mode, emission factors, transfer coefficients, the 62-hour window, carbon brackets and demand scenarios.

The implementation makes the following explicit choices where source details are absent:

- **Network direction:** edges are directed. Add both directions explicitly for a symmetric connection. No automatic reverse links or inferred distances are created.
- **Route space:** routes cannot revisit a city. This is a defined modelling restriction, not proof that cycles could never help a different model with early-arrival penalties.
- **Transfer availability:** a listed mode pair is symmetric and available at every intermediate city. Missing pairs prohibit switching. There is no initial loading or final unloading charge. City-specific terminals are not represented.
- **Freight rate:** either one explicit CNY/(tonne km) rate per mode or the historical three rates at 500/1,000 km boundaries. The five-node legacy fixture retains flat rates; generated 23-city benchmarks use the historical bands.
- **Transfer time:** hours per 1,000 tonnes multiplied by quantity/1,000. Mode-preserving intermediate stops incur no transfer penalty.
- **Carbon:** progressive marginal pricing across total transport-plus-transfer emissions for this shipment, separately in each scenario. This is a model coefficient, not a statement of current tax law.
- **Time window:** early arrival incurs waiting/storage cost until the lower bound; late arrival incurs delay cost after the upper bound. Travel-plus-transfer time is reported separately from waiting. A hard deadline additionally prohibits any positive lateness in any scenario.
- **Uncertainty:** all scenarios use the same route. Quantity, speed multiplier and transport-rate multiplier are explicit deterministic inputs. There is no hidden random resampling. Speed multipliers do not alter transfer time; rate multipliers do not alter transfer prices or carbon prices.
- **Risk objective:** `expected_cost + risk_weight * (worst_cost - expected_cost)`, with weight in [0, 1]. Zero minimizes expected cost; one minimizes worst scenario cost. This is a new optional risk preference, not the unrecovered historical robustness equation or a CVaR model.
- **Emission/capacity constraints:** an optional absolute kg limit applies to every scenario. Optional edge capacity is also checked against every scenario. A historical relative-reduction condition requires an independently justified baseline converted to an absolute cap.

No coefficients have been calibrated to force a match to the old presentation's figures. In particular, its 500 CNY rail-water transfer differs from the workbook's 250 CNY at 100 tonnes; that discrepancy remains documented.

## Priority decoder

Each directed mode-edge gets an integer priority in [0, E-1], where E is the number of edges. At a city, the decoder tries outgoing edges in descending priority, breaking ties by input index. It backtracks when a branch cannot reach the destination without revisiting a city or using an unavailable transfer. It never inserts an unlisted connection.

This is an edge-priority replacement for the historical decoder, not a replica. The recovered original uses 69 priorities attached to expanded destination nodes and has no backtracking. Every route allowed by the current city-simple model can be expressed by assigning its edges higher priorities than the others. Tests exercise that property on the fixture. A 100,000-state limit aborts decoding explicitly rather than misclassifying an unfinished search as infeasible.

Cost constraints are evaluated after decoding. The decoder does not secretly search for a cheaper or deadline-feasible alternative; Geatpy searches the priority space. Constraint violation is nonnegative, with deadline excess normalized by max(1, deadline) and emission excess normalized by max(1, cap). Zero is feasible. This avoids an arbitrary big-M cost penalty.

## GA variants and equal-budget comparison

The implementation uses the separately installed [Geatpy framework](https://github.com/geatpy-dev/geatpy), a custom `ea.Problem`, integer `RI` encoding and its [SEGA template](https://github.com/geatpy-dev/geatpy/blob/v2.7.0/geatpy/algorithms/soeas/GA/soea_SEGA_templet.py). It uses the framework's operators, not a Python fallback labelled as Geatpy.

The new population-level adaptation is deliberately explicit:

```text
spread = standard deviation of feasible costs / max(1, abs(mean feasible cost))
convergence = 1 / (1 + spread)                 # spread = 0 if none are feasible
crossover probability = 0.60 + 0.35 * convergence
mutation probability = min(0.50, (1 + 4 * convergence) / chromosome dimension)
```

The incumbent is ranked first by constraint violation, then by objective. After 20 generations without an improvement by default, all current individuals except the best are replaced with random individuals. Fitness is recomputed and restart evaluations are counted. The last generation does not restart. The incumbent remains available through Geatpy's elitist search and best-individual archive.

These formulas and replacement fraction are **new design choices**, not the exact original per-individual formula. `--baseline`, `--no-adaptive` and `--no-catastrophe` expose four ablation modes. The Geatpy integration reports actual extra restart evaluations.

[`native_ga.py`](../routing/native_ga.py) provides the same four conceptual variants without claiming to be Geatpy. Each generation evaluates exactly the configured population, including catastrophe generations, so baseline, adaptive-only, catastrophe-only and combined runs have equal candidate-evaluation budgets. It uses tournament selection, two-point crossover, random-reset mutation and parent-offspring elite selection. This compact reference makes the experiment auditable on platforms where the historical Geatpy binary cannot load.

The pinned release wheel contains an `outFunc` type-check defect: it compares `type(callback)` with the string `'function'`, rejecting ordinary functions as well as callable objects. `FreightSEGA` therefore extends the generation-statistics hook after invoking the parent implementation and leaves `outFunc=None`. It does not patch the installed library or replace its evolutionary operators. The wheel's SHA-256 is pinned in the requirements file because release-wheel code differs from the current GitHub branch.

## Running and interpreting output

Dependency-free model and exact search, Python 3.10+:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B -m routing examples/synthetic-network.json --solver exact
python3 -B -m routing examples/synthetic-network.json --solver native-ga --seed 42
```

Real Geatpy integration target: Linux x86_64, CPython 3.10, NumPy 1.26.4, Matplotlib 3.8.4, Geatpy 2.7.0. The requirements file points directly to the [official release wheel](https://github.com/geatpy-dev/geatpy/releases/tag/v2.7.0). It is not a portable requirements file for every platform. Geatpy's README lists an older compatibility range; release assets include additional versions, so compatibility is determined by the selected wheel and tested environment, not guessed from the README alone.

The compiled wheel also requires GNU OpenMP (`libgomp.so.1`). CI installs Debian `libgomp1`; [`Dockerfile.geatpy`](../Dockerfile.geatpy) pins the same dependency and an amd64 Python 3.10 base image.

```bash
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install --no-cache-dir -r requirements-geatpy.txt
MPLBACKEND=Agg REQUIRE_GEATPY=1 python -m unittest discover -s tests -v
python -m routing examples/synthetic-network.json --solver geatpy --seed 42
python -m routing examples/synthetic-network.json --solver geatpy --seed 42 --baseline
```

On macOS ARM, run `sh tools/run_geatpy_tests.sh`. Docker executes the official x86-64 wheel through a Linux amd64 container while mounting the repository read-only. All 12 real-library tests and the CLI fixture were run successfully on 27 September 2026; see [`GEATPY_VALIDATION.md`](GEATPY_VALIDATION.md). Run `sh tools/run_geatpy_experiment.sh` to regenerate the 30-seed ablation and figures analyzed in [`GEATPY_RESULTS_ANALYSIS_CN.md`](GEATPY_RESULTS_ANALYSIS_CN.md). [CI](https://github.com/jetfan-xin/carbon-aware-multimodal-routing/actions/workflows/tests.yml) independently requires Geatpy on Linux/Python 3.10, and a missing library fails that job.

JSON output includes the route, modes, per-scenario cost breakdown, time and emissions, expected/worst/objective costs, feasibility, seed, evaluation count, restart trace and SHA-256 of the input file. Money is not rounded during optimization; round only for display. Exit status 0 means a solution, 2 means no solution found (or exact infeasibility), and 1 means invalid input, environment failure or a search-limit error.

The full-flow utilities are:

```bash
python3 -B tools/generate_synthetic_benchmark.py --nodes 23 --orders 100000 \
  --network-output /tmp/network.json --orders-output /tmp/orders.json
python3 -B tools/run_full_pipeline.py /tmp/network.json /tmp/orders.json --solver dijkstra
python3 -B tools/run_scalability_benchmark.py --nodes 23 --orders 100000 \
  --population 80 --generations 100 --seeds 0,1,2,3,4,5,6,7,8,9
```

The 100,000 rows generated here are synthetic orders calibrated only to aggregate historical characteristics. The scale claim must always retain that qualifier.

`optimal` from exhaustive search means optimal **only within this explicitly restricted city-simple model**. Enumeration is limited to eight cities and 100,000 expanded states; it raises on exceeding a bound rather than returning a partial optimum. Geatpy returns `feasible-heuristic`, never an unsupported optimality certificate. Its failure to find a feasible route is not proof that none exists.

## Validation and remaining limits

For the synthetic fixture, exhaustive enumeration finds `Origin -> RiverHub -> RailHub -> Destination`, all water. The expected cost is 5,586.912 CNY: 1,200 km times mean demand 102.1 tonnes times `(0.045 + 0.012 * 0.05)` CNY/(tonne km). The high-demand scenario costs 8,208 CNY. There are no transfers or late penalties on that route.

Tests compare real Geatpy and exact costs with seeds 0, 7 and 42; exercise independent adaptation/catastrophe flags; force restart execution; verify equal native-GA candidate budgets; check repeatability, closures, capacity, batching, generated 23-city/754-edge scale and SVG output. Separate hand calculations cover mode changes, waiting, lateness and carbon-bracket boundaries.

For the row-level historical network, prepare an authorized local JSON instance, explicitly choose a distance-workbook version and direction convention, and keep non-redistributable mapping rows outside the public repository. The checked-in aggregate profile and synthetic generator reproduce scale and mode availability without copying the raw table. Exact enumeration is not intended for the 23-city graph; use the state-Dijkstra comparison and GA variants.
