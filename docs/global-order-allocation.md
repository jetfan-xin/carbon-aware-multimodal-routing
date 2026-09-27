# Global order allocation

## Why allocation replaces repeated single-route search

The three-node/five-edge facility graph is valuable for checking cost, time, emissions and transfer logic, but one shipment has only four route alternatives. A GA is unnecessary there. The maintained allocation problem instead assigns many orders that compete for the same rail/water capacity and share one progressive carbon schedule.

For order `i`, gene `x_i` selects one candidate from its bounded pool:

```text
min sum_i noncarbon_cost(i, x_i) + CarbonCost(sum_i emissions(i, x_i))

subject to
  sum_i tonnes(i) * use(i, x_i, resource) <= resource tonnes capacity
  sum_i units(i)  * use(i, x_i, resource) <= resource unit capacity
  arrival(i, x_i) <= deadline(i)
  sum_i emissions(i, x_i) <= portfolio emissions cap  [optional]
```

Ranking is lexicographic: total normalized constraint violation, total cost, then emissions. Candidate retention protects the best-ranked, fastest, lowest-emission, capacity-independent and mode-diverse alternatives so a hard cap is not made artificially infeasible during preprocessing.

## Five GA variants

| Method | Adaptive rates | Partial restart | Opportunity-loss archive |
| --- | --- | --- | --- |
| fixed | No | No | No |
| adaptive | Yes | No | No |
| catastrophe | No | Yes | No |
| combined | Yes | Yes | No |
| hybrid-seeded | Yes | Yes | Yes |

All use ternary tournament selection, contiguous-segment crossover, integer mutation, parent--offspring elitism and capacity-aware random initialization. Hard-cap experiments also give every method the same low-emission constraint seed.

## Experiment roles

1. **Facility evaluator check:** 12 model orders on a three-node/five-edge graph. A four-order prefix has 3,072 combinations and is exhaustively verified. All methods reach CNY 68,449.24 on the full simple portfolio, so this case does not demonstrate GA superiority.
2. **Synthetic 23-city algorithm stress test:** 48 synthetic orders, 23 OD pairs, 145 edges and 96 shared resources. Thirty seeds per GA use 100 individuals x 150 generations. The best-known hybrid result is CNY 304,051.85, 18.39% below the deadline-greedy baseline within this instance.
3. **Corridor policy experiment:** field-calibrated Chongqing--Yangshan alternatives plus deterministic model orders and assumed planning capacity. It tests demand, deadlines, carbon prices and hard reduction targets, not enterprise data scale.

The first case checks arithmetic, the second checks search behavior, and the third checks direction and policy trade-offs. None is a deployment trial.
