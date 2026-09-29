# Corridor scenario design

The corridor experiments use public/operator values only where their scope is explicit. Deadline, payload, demand, capacity and carbon-price scenarios remain model inputs.

The deterministic route grid varies payload, deadline, time case and carbon shadow price. The global policy grid varies three demand sizes, three deadline profiles, three carbon prices and four hard emissions targets. Reduction targets are anchored to public policy percentages only as transparent stress cases:

- 9.5%: China's 2030 operating-transport intensity target;
- 20% and 30%: IMO 2030 absolute-emissions checkpoint and striving level, used only as stress percentages.

Neither policy is represented as a direct shipment-level legal cap on domestic Chongqing--Shanghai freight. The national ETS price is used as a shadow-price reference; freight is not claimed as a directly covered 2025 compliance sector.

In the corridor-only grid, each hard cap is calculated from the best feasible uncapped hybrid screening result under the same demand, deadline and carbon-price case. That reference is reproducible but heuristic. Candidate retention preserves cheapest, fastest, lowest-emission, capacity-independent and mode-diverse routes before allocation.

The policy-calibrated 23-city extension defines every reduction cap from a common **single-trunk reference** in the same demand, deadline and carbon-price scenario. Each order independently selects its minimum-cost deadline-feasible pure-water, pure-rail or pure-road candidate and cannot change mode. A 20% target means 20% below the sum of those selected orders' emissions. Cross-order shared capacity is deliberately excluded from this reference comparator and remains enforced in every evaluated allocation. OD span and cargo class set 48/60/72-hour limits; water uses explicit 24-hour departures with 20-tonne/two-unit capacity. Handling, port dwell, lock delay, reliability buffer, schedule waiting and transfer time all count toward feasibility. The topology, OD portfolio and operating values remain synthetic model inputs, not observed freight-network data.

The complete machine-readable design is [`policy_experiment.json`](../data/policy_experiment.json).
