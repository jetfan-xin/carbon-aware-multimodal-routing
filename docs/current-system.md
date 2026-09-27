# Maintained routing and allocation system

The maintained system turns the historical single-route case into a reproducible analysis pipeline while preserving the original snapshot separately.

## Components

- [`model.py`](../routing/model.py): validated network, route evaluation, exact enumeration and state-Dijkstra baseline.
- [`geatpy_solver.py`](../routing/geatpy_solver.py): optional Geatpy integration for the maintained route model.
- [`native_ga.py`](../routing/native_ga.py): dependency-free route-level GA ablations.
- [`facility_data.py`](../routing/facility_data.py) and [`facility_network.py`](../routing/facility_network.py): evidence registry and field-classified calibrated cases.
- [`allocation.py`](../routing/allocation.py): route/departure candidates, shared capacities, aggregate carbon accounting, hard emissions cap, exact and greedy solvers.
- [`allocation_ga.py`](../routing/allocation_ga.py): fixed, adaptive, catastrophe, combined and hybrid-seeded global allocation.
- [`pipeline.py`](../routing/pipeline.py): order consolidation, edge-state filtering and SVG route output.

One integer gene selects one route/departure candidate for each indivisible model order. The objective minimizes non-carbon operating cost plus a progressive carbon charge applied once to portfolio emissions. Feasibility covers route validity, deadlines, shared tonnes/units capacity and an optional portfolio emissions cap.

Every hard-cap run gives all GA variants the same capacity-aware low-emission seed. This is common constraint handling. The hybrid variant alone adds an opportunity-loss greedy incumbent archive. Results remain heuristic unless an explicitly named small candidate set was exhaustively enumerated.

The standard-library test suite covers validation, route evaluation, candidate generation, shared capacity, hard emissions caps, exact micro-oracles, generated outputs and provenance checks. The optional Geatpy 2.7.0 wheel is tested in a pinned Linux amd64/Python 3.10 container because its old x86-64 binary does not load natively on macOS ARM.

See [the integrated report](PROJECT_REPORT.md), [method](method.md), [implementation](implementation.md) and [result record](results.md).
