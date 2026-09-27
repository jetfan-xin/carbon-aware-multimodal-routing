# Original `GA_code`: evidence-based technical analysis

Audit date: 27 September 2026
Stable source ID: `recovered-ga-code-2022-11-23`

## Executive finding

The recovered directory is project-specific Python/Geatpy code for one Chongqing-to-Shanghai multimodal route-search case. It expands 23 cities into three mode layers (road, rail and water), decodes a 69-integer priority chromosome into one route, calculates transport, transfer, time-window and carbon costs, and minimizes their sum as one objective.

The code is a real genetic-algorithm problem definition, but the evolutionary loop is supplied by the third-party Geatpy `soea_SEGA_templet`. Project-specific contributions are the data loaders, mode-layer graph, priority decoder, cost model and template configuration. Geatpy itself is not personal implementation.

The saved entry point contains `NIND=100000` and `MAXGEN=1` ([`main.py`](../historical/GA_code/main.py#L18)). `MAXGEN` is an editable experiment parameter, not evidence that multi-generation runs never occurred. Archived terminal output and the defence document record generation 99, 100 generations and 100,000 evaluations. They support historical execution, while the exact source revision for the documented adaptive operators and 20-generation random injection has not been recovered.

## Entry point and call chain

```text
main.py
  -> ga.MyProblem
       -> input.py: Excel distance and parameter loaders
       -> utils.py: city IDs, mode labels and transfer counting
       -> ga.MyProblem.decode: priority chromosome -> route
       -> calculate.py: transport, transfer, time and carbon cost
  -> geatpy.soea_SEGA_templet
  -> geatpy.optimize
  -> terminal result and Geatpy output directory
```

The byte-exact project snapshot is under [`historical/GA_code`](../historical/GA_code/). The original workbooks and absolute Windows paths are intentionally not redistributed. [`compatibility/run_original.py`](../compatibility/run_original.py) supplies external paths without modifying the snapshot.

## Encoding and graph

- `N=23`, `dim=23*3=69` ([`ga.py`](../historical/GA_code/ga.py#L14)).
- Each city has a road-layer, rail-layer and water-layer node.
- Each chromosome is 69 bounded integer values in `[0, 68]` ([`ga.py`](../historical/GA_code/ga.py#L22)). Values are priorities, not a direct city sequence.
- The distance workbook is expanded into mode-layer directed edges by adding offsets 0, 23 or 46 ([`input.py`](../historical/GA_code/input.py#L22)).
- At each city the decoder examines outgoing nodes in all three layers and selects the reachable expanded node carrying the largest chromosome value ([`ga.py`](../historical/GA_code/ga.py#L61)).
- A change in the source-node layer between consecutive edges is interpreted as a mode transfer ([`calculate.py`](../historical/GA_code/calculate.py#L34)).

The decoder is greedy and has no backtracking, visited-node set or explicit dead-end check. A dead end, negative fallback index or cycle can therefore fail or loop. Duplicate chromosome priority values are allowed. The recovered code does not repair invalid routes.

## Objective and constraints

The problem has one minimization objective (`M=1`), not a Pareto multi-objective formulation. [`aimFunc`](../historical/GA_code/ga.py#L87) computes:

```text
objective = transport cost + transfer cost + time-window cost + carbon cost
```

Transport cost uses three distance bands below 500 km, 500--1,000 km and at least 1,000 km ([`calculate.py`](../historical/GA_code/calculate.py#L19)). Transfer cost depends on counts of road--rail, road--water and rail--water changes ([`calculate.py`](../historical/GA_code/calculate.py#L35)). Travel time is distance divided by average speed plus transfer time proportional to tonnes. Early arrival incurs storage cost and late arrival incurs a penalty ([`calculate.py`](../historical/GA_code/calculate.py#L50)); the time window is therefore a soft penalty, not a hard constraint.

Emissions equal tonne-kilometre transport emissions plus per-tonne transfer emissions. Carbon cost uses a progressive quick-deduction formula ([`calculate.py`](../historical/GA_code/calculate.py#L63)). The recovered implementation has an indexing defect in the second and later brackets because `Yk[-1]` is read while `Yk` is still empty. The archived final route remained in the first bracket, so that branch was not required for the reproduced case.

`pop.CV` is initialized to zero and never populated ([`ga.py`](../historical/GA_code/ga.py#L87)). Consequently, the recovered problem passes no explicit constraint violation to Geatpy. Time windows and carbon are monetized objective terms; they are not hard constraints.

## Demand uncertainty and robustness

The input loader reads three scenario quantities `Q` and probabilities `P` ([`input.py`](../historical/GA_code/input.py#L88)). However, `MyProblem` sets `self.qt=100`, and every cost call uses that constant ([`ga.py`](../historical/GA_code/ga.py#L50)). The loaded scenarios and probabilities do not flow into the recovered objective. Therefore the recovered source does not implement stochastic expectation, worst-case cost or robust optimization, even if those ideas appeared in presentation material.

## Genetic operators and historical adaptive claims

The entry point configures Geatpy's SEGA template with real/integer encoding ([`main.py`](../historical/GA_code/main.py#L22)). Geatpy 2.7.0 supplies the standard evolutionary lifecycle and its operators. Those framework internals are dependencies, not project-authored source.

Historical presentation and terminal evidence show a 100-generation run and describe adaptive crossover/mutation plus random-individual injection after 20 unchanged generations. The seven-file snapshot does not contain those formulas or controller code. The correct evidence statement is:

- multi-generation historical execution: supported by archived outputs;
- project-specific route model and fitness: confirmed in recovered code;
- exact adaptive/catastrophe source revision: not recovered;
- third-party Geatpy selection/crossover/mutation loop: framework behavior, not personal code.

## Reproduced historical calculation

An isolated compatibility run reproduced the archived route `Chongqing --water--> Jiujiang --rail--> Anqing --rail--> Shanghai` with the recovered formulas and authorized workbook copy:

- transport cost: CNY 9,618.65;
- transfer cost: CNY 500.00;
- total time: 61.2667 h;
- transport/transfer emissions: 3,069.6 / 11.3 kg;
- carbon cost: CNY 154.045;
- floating total: CNY 10,272.695.

This validates the route calculation against the archived CNY 10,272.69 display. It does not recreate the old Geatpy environment, random population or exact evolutionary trajectory.

## Confirmed defects and limits

1. Absolute Windows paths make the snapshot non-portable.
2. City IDs are derived from a Python `set`, so intermediate ID order can vary by runtime.
3. The greedy decoder lacks cycle/dead-end protection.
4. Scenario demand and probability are loaded but unused.
5. Constraint violation is never set beyond zeros.
6. Carbon brackets above the first contain an indexing defect.
7. Printing every evaluated individual severely affects performance.
8. The code optimizes one fixed 100-tonne case and cannot prove global optimality.

These limits do not erase the historical contribution. They define what can be defended: a personally implemented multimodal encoding, decoder and composite-cost fitness integrated with Geatpy, demonstrated on a 23-city case-study network.
