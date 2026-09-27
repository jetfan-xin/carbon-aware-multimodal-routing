# Corridor scenario design

The corridor experiments use public/operator values only where their scope is explicit. Deadline, payload, demand, capacity and carbon-price scenarios remain model inputs.

The deterministic route grid varies payload, deadline, time case and carbon shadow price. The global policy grid varies three demand sizes, three deadline profiles, three carbon prices and four hard emissions targets. Reduction targets are anchored to public policy percentages only as transparent stress cases:

- 9.5%: China's 2030 operating-transport intensity target;
- 20% and 30%: IMO 2030 absolute-emissions checkpoint and striving level, used only as stress percentages.

Neither policy is represented as a direct shipment-level legal cap on domestic Chongqing--Shanghai freight. The national ETS price is used as a shadow-price reference; freight is not claimed as a directly covered 2025 compliance sector.

Each hard cap is calculated from the best feasible uncapped hybrid screening result under the same demand, deadline and carbon-price case. That reference is reproducible but heuristic. Candidate retention preserves cheapest, fastest, lowest-emission, capacity-independent and mode-diverse routes before allocation.

The complete machine-readable design is [`policy_experiment.json`](../data/policy_experiment.json).
