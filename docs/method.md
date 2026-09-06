# Technical method and implementation evidence

## Decision model

The study chooses an origin-destination route and a transport mode for each leg. Changing mode incurs a transfer, which can affect cost, elapsed time and emissions.

The combined objective described in the final materials is:

```text
total cost = transport cost + transfer cost + time cost + carbon cost

total time = travel time + transfer time

total emissions = transport emissions + transfer emissions
```

Transport components depend on route distance, shipment quantity and mode-specific coefficients. Time cost can include storage or late-delivery penalties. The documents propose a piecewise carbon-cost schedule. The coefficients in this repository are historical modelling inputs, not current prices or current tax policy.

The "economic" objective in the archived comparison excludes carbon cost; the "combined" objective includes it. The emission-constrained option additionally requires at least a 15% reduction in emissions relative to its reference. Comparing economic and combined totals without aligning this definition is misleading.

## Route representation

The surviving screenshots show a `MyProblem(ea.Problem)` subclass, integer decision variables, a chromosome-to-path decoder, and an `aimFunc` that sums edge values. Invalid decoded edges raise an error. They provide evidence of a custom route problem inside [Geatpy](https://github.com/geatpy-dev/geatpy), a third-party evolutionary optimization framework.

Some logs distinguish city indices from larger edge indices. This is consistent with a mode-expanded graph, but the complete graph-building and decoding functions are unavailable. The screenshots include folded code and external references such as `get_distance()` and `transtr()`. They are not a self-contained implementation.

The displayed objective in the screenshot is an edge-cost sum. The screenshot alone does not establish that every carbon, uncertainty and penalty term from the final mathematical description was implemented in that exact revision.

## Evolutionary search design

The final presentation and defense notes describe:

1. Priority-based chromosome encoding of a route.
2. Fitness-dependent crossover and mutation probabilities.
3. A diversity-restoring catastrophe/restart operation after 20 generations without improvement.
4. Demand scenarios and parameter resampling to represent uncertainty.

These are documented design decisions. The exact adaptive formulas, restart implementation, random seeds, feasibility-repair rules and complete run configurations could not be recovered. Accordingly, no claim of reproducing the adaptive solver is made here.

The source describes the routing problem as NP-hard. It is the constrained optimization problem, not "the genetic algorithm itself," that has this complexity characterization. The archived heuristically selected routes should not be described as proven global optima without a bound or exact-solver comparison.

## Uncertainty

One preserved workbook lists three quantity scenarios: 150 tonnes at probability 0.36, 85 tonnes at 0.50, and 40 tonnes at 0.14. The probabilities sum to one and imply a mean quantity of 102.1 tonnes. This is distinct from the final presentation's fixed 100-tonne example.

The documents describe a robustness condition across scenarios, but the complete algebra and implementation needed to reproduce it are not available. The repository retains the scenario inputs and documents this boundary instead of inventing a missing robust objective.

## Implementation status

| Component | Surviving evidence | Repository treatment |
| --- | --- | --- |
| Python/Geatpy route problem | Code screenshots; terminal output | Explain and preserve the screenshots |
| Adaptive operators and restarts | Final slides and defense notes | Document the design; do not claim recovered executable code |
| Data preparation | Workbook inputs; Pandas/MAD description in semifinal report | Record schema, units and provenance |
| Map visualization | Generated Folium/Leaflet HTML | Record provenance; do not ship obsolete CDN-dependent exports |
| Order allocation and graph preprocessing | Design narrative | Not presented as a recovered service |
| Blockchain, settlement and live tracking | Architecture and interface designs | Clearly separated from the routing implementation |
| Results verification | New standard-library Python utility and tests | Explicitly dated 2026 |

## What a faithful future reproduction would need

Recover the custom problem and algorithm classes, input-loader conventions, transport-rate band boundaries, exact network version, parameter configuration, seeds and raw run histories. Validate route feasibility and dimensional consistency first. Only then compare the adaptive search with an unmodified baseline under identical budgets and data.
