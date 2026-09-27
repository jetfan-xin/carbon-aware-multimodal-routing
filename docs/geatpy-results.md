# Geatpy 23-city ablation results

This experiment verifies the maintained route-level integration with the official Geatpy 2.7.0 wheel on one explicitly synthetic 23-city/754-edge directed acyclic network. It does not reproduce the unrecovered historical random state.

Each of five methods ran 30 paired seeds. Fixed, adaptive, catastrophe and combined variants used the same initial random population for a given seed; the hybrid added a graph-heuristic route. At equal candidate budgets, adaptive plus catastrophe improved the objective by 11.46% on average relative to fixed. The hybrid started from a much stronger deterministic route, but the GA did not improve that route; its benefit must therefore be attributed to heuristic initialization rather than genetic operators.

DFS establishes reachability. Topological sorting verifies and orders the DAG; it does not create graph connectivity. The route experiment does not measure order throughput or enterprise data scale.

The checked-in result, per-seed runs and figures are under [`benchmarks/geatpy-23city-ablation`](../benchmarks/geatpy-23city-ablation/). Docker verification details are in [`GEATPY_VALIDATION.md`](GEATPY_VALIDATION.md).
