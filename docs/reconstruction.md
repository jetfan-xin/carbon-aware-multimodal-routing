# Runnable optimizer: September 2026 reconstruction

## Status and scope

This is newly implemented software based on the surviving project description and parameter snapshots. It is **not recovered 2022 code** and does not reproduce the archived Chongqing-Shanghai totals. The original drive was kept read-only. Historical data and screenshots were not overwritten to fit the new implementation.

The executable scope is one shipment, one origin-destination route, road/rail/inland-water mode choices, transfer accounting, delivery constraints and scenario evaluation. It excludes order allocation, capacity scheduling, timetables, blockchain services and a web interface.

## Implementation map

| File | Responsibility |
| --- | --- |
| [model.py](../routing/model.py) | Input validation, directed graph, priority decoding, cost model, exhaustive baseline |
| [geatpy_solver.py](../routing/geatpy_solver.py) | Real Geatpy Problem/SEGA integration, operator adaptation and restarts |
| [CLI](../routing/__main__.py) | JSON input, solver selection, reproducible JSON output and input hash |
| [Synthetic example](../examples/synthetic-network.json) | Five-city test fixture with a dead end, a cycle and parallel transport modes |
| [Core tests](../tests/test_routing.py) | Hand-calculated costs, boundaries, scenarios, graph validation and exact checks |
| [Integration tests](../tests/test_geatpy_integration.py) | Real Geatpy runs, multiple seeds, restarts, constraints and baseline comparison |

## Recovered inputs versus new decisions

The [parameter snapshot](../data/parameter_snapshot.json) supplies mode speeds, three candidate rates per mode, emission factors, transfer coefficients, the 62-hour window, carbon brackets and demand scenarios.

The reconstruction makes the following explicit choices where source details are absent:

- **Network direction:** edges are directed. Add both directions explicitly for a symmetric connection. No automatic reverse links or inferred distances are created.
- **Route space:** routes cannot revisit a city. This is a defined modelling restriction, not proof that cycles could never help a different model with early-arrival penalties.
- **Transfer availability:** a listed mode pair is symmetric and available at every intermediate city. Missing pairs prohibit switching. There is no initial loading or final unloading charge. City-specific terminals are not represented.
- **Freight rate:** one explicit CNY/(tonne km) rate per mode. The example selects the first listed historical coefficient. Missing historical rate-band boundaries are not guessed.
- **Transfer time:** hours per 1,000 tonnes multiplied by quantity/1,000. Mode-preserving intermediate stops incur no transfer penalty.
- **Carbon:** progressive marginal pricing across total transport-plus-transfer emissions for this shipment, separately in each scenario. This is a model coefficient, not a statement of current tax law.
- **Time window:** early arrival incurs waiting/storage cost until the lower bound; late arrival incurs delay cost after the upper bound. Travel-plus-transfer time is reported separately from waiting. A hard deadline additionally prohibits any positive lateness in any scenario.
- **Uncertainty:** all scenarios use the same route. Quantity, speed multiplier and transport-rate multiplier are explicit deterministic inputs. There is no hidden random resampling. Speed multipliers do not alter transfer time; rate multipliers do not alter transfer prices or carbon prices.
- **Risk objective:** `expected_cost + risk_weight * (worst_cost - expected_cost)`, with weight in [0, 1]. Zero minimizes expected cost; one minimizes worst scenario cost. This is a new optional risk preference, not the unrecovered historical robustness equation or a CVaR model.
- **Emission cap:** an optional absolute kg limit applies to every scenario. A historical relative-reduction condition requires the user to select an independently justified baseline and convert it to an absolute cap.

No coefficients have been calibrated to force a match to the old presentation's figures. In particular, its 500 CNY rail-water transfer differs from the workbook's 250 CNY at 100 tonnes; that discrepancy remains documented.

## Priority decoder

Each directed mode-edge gets an integer priority in [0, E-1], where E is the number of edges. At a city, the decoder tries outgoing edges in descending priority, breaking ties by input index. It backtracks when a branch cannot reach the destination without revisiting a city or using an unavailable transfer. It never inserts an unlisted connection.

This is an edge-priority replacement for the incomplete historical decoder, not a claim that its mode-layer chromosome was identical. Every allowed city-simple route can be expressed by assigning its edges higher priorities than the others. Tests exercise that property on the fixture. A 100,000-state limit aborts decoding explicitly rather than misclassifying an unfinished search as infeasible.

Cost constraints are evaluated after decoding. The decoder does not secretly search for a cheaper or deadline-feasible alternative; Geatpy searches the priority space. Constraint violation is nonnegative, with deadline excess normalized by max(1, deadline) and emission excess normalized by max(1, cap). Zero is feasible. This avoids an arbitrary big-M cost penalty.

## Adaptive Geatpy search

The implementation uses the separately installed [Geatpy framework](https://github.com/geatpy-dev/geatpy), a custom `ea.Problem`, integer `RI` encoding and its [SEGA template](https://github.com/geatpy-dev/geatpy/blob/v2.7.0/geatpy/algorithms/soeas/GA/soea_SEGA_templet.py). It uses the framework's operators, not a Python fallback labelled as Geatpy.

The new population-level adaptation is deliberately explicit:

```text
spread = standard deviation of feasible costs / max(1, abs(mean feasible cost))
convergence = 1 / (1 + spread)                 # spread = 0 if none are feasible
crossover probability = 0.60 + 0.35 * convergence
mutation probability = min(0.50, (1 + 4 * convergence) / chromosome dimension)
```

The incumbent is ranked first by constraint violation, then by objective. After 20 generations without an improvement by default, all current individuals except the best are replaced with random individuals. Fitness is recomputed and restart evaluations are counted. The last generation does not restart. The incumbent remains available through Geatpy's elitist search and best-individual archive.

These formulas and replacement fraction are **new design choices**, not the original per-individual fitness-adaptation formula. `--baseline` disables adaptation and restarts, retaining the standard SEGA operator settings. The same generation/population settings are not equal evaluation budgets when restarts occur; output includes actual evaluations. No performance-superiority claim is made.

## Running and interpreting output

Dependency-free model and exact search, Python 3.10+:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B -m routing examples/synthetic-network.json --solver exact
```

Real Geatpy integration target: Linux x86_64, CPython 3.10, NumPy 1.26.4, Matplotlib 3.8.4, Geatpy 2.7.0. The requirements file points directly to the [official release wheel](https://github.com/geatpy-dev/geatpy/releases/tag/v2.7.0). It is not a portable requirements file for every platform. Geatpy's README lists an older compatibility range; release assets include additional versions, so compatibility is determined by the selected wheel and tested environment, not guessed from the README alone.

```bash
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install --no-cache-dir -r requirements-geatpy.txt
MPLBACKEND=Agg REQUIRE_GEATPY=1 python -m unittest discover -s tests -v
python -m routing examples/synthetic-network.json --solver geatpy --seed 42
python -m routing examples/synthetic-network.json --solver geatpy --seed 42 --baseline
```

The original development Mac uses Python 3.13 on ARM; no Geatpy environment or large dependency cache was installed there. [CI](https://github.com/jetfan-xin/carbon-aware-multimodal-routing/actions/workflows/tests.yml) runs dependency-free tests on Python 3.13 and mandatory real-library tests on Linux/Python 3.10. Missing Geatpy fails the integration job; local skipped tests do not count as verified integration.

JSON output includes the route, modes, per-scenario cost breakdown, time and emissions, expected/worst/objective costs, feasibility, seed, evaluation count, restart trace and SHA-256 of the input file. Money is not rounded during optimization; round only for display. Exit status 0 means a solution, 2 means no solution found (or exact infeasibility), and 1 means invalid input, environment failure or a search-limit error.

`optimal` from exhaustive search means optimal **only within this explicitly restricted city-simple model**. Enumeration is limited to eight cities and 100,000 expanded states; it raises on exceeding a bound rather than returning a partial optimum. Geatpy returns `feasible-heuristic`, never an unsupported optimality certificate. Its failure to find a feasible route is not proof that none exists.

## Validation and remaining limits

For the synthetic fixture, exhaustive enumeration finds `Origin -> RiverHub -> RailHub -> Destination`, all water. The expected cost is 5,586.912 CNY: 1,200 km times mean demand 102.1 tonnes times `(0.045 + 0.012 * 0.05)` CNY/(tonne km). The high-demand scenario costs 8,208 CNY. There are no transfers or late penalties on that route.

Tests compare real Geatpy and exact costs with seeds 0, 7 and 42, with adaptation enabled and disabled; force restart execution; check repeatability; and test hard-deadline and infeasible cases. Separate hand calculations cover mode changes, waiting, lateness and carbon-bracket boundaries. These establish behavior on controlled examples, not scalability or the historical competition's reported speed.

To use the 23-city historical network, first prepare an authorized local JSON instance in the same schema, explicitly choose a distance-workbook version, direction convention and rates, and keep non-redistributable raw mapping data out of the public repository. Exact baseline enumeration is not intended for that network. Further work would include larger-network benchmarks, scenario calibration, city-specific transfer facilities and independently sourced transport-rate bands.
