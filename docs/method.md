# Recovered technical method

## Graph and chromosome

The historical implementation fixes 23 base cities and expands each into three transport-mode layers, producing 69 node IDs: road 0-22, rail 23-45 and water 46-68. Each populated mode distance becomes a directed edge inside its layer. The workbook contains one row for each unordered city pair, so the code does not automatically create reverse edges.

A chromosome is a 69-element integer vector with every gene bounded from 0 through 68. Gene values are priorities associated with expanded destination nodes; duplicates are allowed. This is not a city sequence and not a binary edge-selection vector.

Intermediate city IDs are built through `list(set(cities))`, so only Chongqing 0 and Shanghai 22 are fixed. Other IDs can vary with Python hash/set order.

## Greedy decoding

The decoder starts at base city 0. At each city it retrieves outgoing neighbours from the road, rail and water copies of that city, finds the highest-priority destination in each nonempty list, then selects the mode whose candidate has the greatest priority. The expanded destination is converted back to a base-city ID and the process repeats until city 22.

There is no visited set, cycle prevention, backtracking, route repair, maximum step count or explicit unreachable-state handling. The retained network's complete forward road connectivity makes destination progress likely for its particular city order, but the decoder is not safe for a general graph.

## Single objective

The code declares `M=1` and minimizes:

```text
C = C_transport + C_transfer + C_time + C_carbon
```

- Transport cost multiplies quantity, distance and one of three mode rates selected at 500 km and 1,000 km boundaries.
- Transfer cost counts changes among road/rail/water. A duplicated counting loop makes the cost function count every change twice.
- Time is travel time plus transfer time. Arrival before 0 hours or after 62 hours produces a soft storage or delay cost. There is no hard deadline.
- Emissions are transport plus transfer emissions. The code monetizes them via a carbon schedule; it has no emission cap. The quick-deduction implementation works only in the first bracket and raises `IndexError` at higher brackets.

The constraint matrix is initialized to zero and never changed. Best candidates are therefore ranked only by the scalar cost. No capacity or service constraint is encoded.

## Demand scenarios

The loader reads 150 tonnes at probability 0.36, 85 tonnes at 0.50 and 40 tonnes at 0.14. The optimizer nevertheless fixes `self.qt = 100`; neither `Q` nor `P` enters decoding or any objective calculation. The recovered executable code therefore does not implement stochastic, expected-value, robust or scenario-constrained optimization.

## What runs in Geatpy

The saved entry point constructs `ea.soea_SEGA_templet` with RI encoding. Geatpy 2.7.0 supplies tournament selection, two-point crossover at 0.7, breeder-GA mutation at `1/Dim`, parent-offspring merging and fitness-based elite selection. The project-specific code supplies the problem, chromosome interpretation, decoder and objective.

The retained `main.py` happens to contain `NIND=100000, MAXGEN=1`. `MAXGEN` is a mutable experiment parameter, not an implementation boundary. With that particular value the template stops after initial evaluation; changing it activates the complete SEGA loop. Separate 2022 logs record generation index 99 and 100,000 evaluations, while the defense document reports 100 generations and embeds the corresponding trace plot. Those artifacts confirm that full multi-generation runs occurred historically.

The byte-exact seven-file snapshot does not embed the custom adaptive controller described in the defense material. The contemporaneous document nevertheless specifies adaptive crossover/mutation and random population injection after 20 unchanged generations. The evidence-safe conclusion is that the design and historical runs are documented, while the exact source revision/configuration that produced each artifact has not yet been matched. The fitness-spread formula in the maintained implementation is explicitly a later engineering choice.

## Modern end-to-end framework

The extension organizes the implemented workflow as greedy deadline-compatible order batching; DFS reachability analysis and deterministic topological sorting for acyclic directed networks; route search; transport, transfer, scheduled-service/time-window and carbon evaluation under demand scenarios; and five-way fixed/adaptive/catastrophe/combined/hybrid-seeded GA comparison.

DFS establishes which nodes and the destination are reachable. Topological sorting validates and orders a directed acyclic graph; it does not itself create the connectivity graph. This distinction is retained for technically precise interview explanations. The scenario objective combines expected and worst-case cost through a configurable risk weight, so the modern extension can run the robust-combination formulation that the recovered 2022 executable did not activate.

For multiple orders, carbon brackets apply to aggregate portfolio emissions. The earlier homogeneous allocator remains as a compact sensitivity tool. The global allocator now gives every indivisible order one integer gene selecting a route/departure candidate. Orders jointly consume timed-departure capacity or explicitly synthetic planning-horizon lane capacity. Feasibility-first ranking covers missing candidates, per-route violations, hard deadlines and shared capacity; the progressive marginal carbon schedule is then applied once to total portfolio emissions.

Candidate generation and allocation are intentionally separate. Exact route enumeration is used only on small graphs. Large graphs use bounded, mode-diverse beam search to retain road, rail, water and mixed candidates; this is preprocessing, not an optimality proof. The small allocation oracle enumerates the Cartesian product of candidate choices. The scalable methods are earliest-deadline-first greedy allocation, opportunity-loss greedy allocation and five order-level GA variants. All GA variants use randomized capacity-feasible initialization, tournament selection, slice crossover, per-gene mutation and parent-offspring elitism.

The formal allocation experiment uses a second-generation adaptive controller based on mean locus impurity and stagnant generations. With the selected coefficients it bounds mutation to an expected 1.25--2.75 genes per child under a 3.0 hard cap, raises crossover from 0.72 to at most 0.85, and replaces 25% of the population after 30 stagnant generations while retaining unique elites. The hybrid keeps an opportunity-loss greedy solution in an external incumbent archive instead of replacing a random initial individual; its 288 candidate checks are reported separately. The earlier feasible-cost-spread controller, full restart and deadline-seeded population remain callable only as explicit legacy comparisons. Configuration selection used seeds 30--39 and paired validation used untouched seeds 40--69; see [`ALLOCATION_CONTROL_TUNING_CN.md`](ALLOCATION_CONTROL_TUNING_CN.md).

## Facility-network admission

The current extension no longer treats an official port plan as proof of a directed mode edge. Candidate generation, facility capability and transport service are separate layers. A core node must resolve to a physical port area, terminal or freight station. A service can enter the routing model only when both endpoints, direction, cargo compatibility, validity date, distance and service time are present; missing tariff or handling scope must remain explicit rather than being backfilled from an unrelated route.

Historical and current snapshots are evaluated separately. Later facilities or services cannot be backdated into the 2022 case. A through liner may pass geographic cities without calling, so intermediate Yangtze cities are not automatically transfer nodes. See [`FACILITY_NETWORK_DESIGN_CN.md`](FACILITY_NETWORK_DESIGN_CN.md).

The numeric analysis layer is deliberately separate. Each numeric edge records field-level provenance and may combine a reported lane price, team-collected distance and labelled time or terminal assumption. Transfers may now carry a `facility_id`: the rail-road change documented at Luchaogang is available only there, while older instances without a facility retain their explicit global default. The Guoyuan-Yangshan case therefore contains one true multileg alternative, Guoyuan—rail→Luchaogang—road→Yangshan, alongside direct road and bundled water services. Exact enumeration compares only these admitted routes; it does not infer calls at Wuhu, Nanjing or every geographic city. See [`FACILITY_NUMERIC_MODEL_CN.md`](FACILITY_NUMERIC_MODEL_CN.md).

## Outputs and optimality

Every candidate prints total cost, time, emissions and component costs. Geatpy is asked to draw and save output under `result`; the final city mapping, heuristic minimum and decoded route are printed. Because GA search provides no bound, the result is not a proof of global optimality.

`map.py` is a separate manual script. It reads 25 coordinates, draws dense background lines and hard-codes highlighted routes and distance labels. It neither imports solver results nor guarantees consistency with the distance workbook.

See the [Chinese original-code analysis](ORIGINAL_GA_CODE_ANALYSIS_CN.md) for function-level line references and [implementation guide](implementation.md) for the safe execution boundary.
