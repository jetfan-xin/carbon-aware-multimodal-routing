# Results, comparisons and validation

## Directly reproduced historical calculation

Using temporary copies of the matching workbooks and the unchanged functions in `historical/GA_code/calculate.py`, the illustrated Chongqing → Jiujiang → Anqing → Shanghai route (water, rail, rail) gives:

| Component | Reproduced value |
| --- | ---: |
| transport cost | 9,618.65 CNY |
| transfer cost | 500.00 CNY |
| time cost | 0.00 CNY |
| carbon cost | 154.045 CNY |
| total | 10,272.695 CNY |
| travel + transfer time | 56.2667 + 5.0000 = 61.2667 h |
| transport + transfer emissions | 3,069.6 + 11.3 = 3,080.9 kg |

This reproduces the presentation total after display rounding. The transfer function reports two changes even though the route changes mode only once: it calls `get_transit_num` and then repeats the same loop. The 500 CNY is therefore evidence of the historical double count, not evidence that the workbook transfer rate is 5 CNY/t.

The probe was a function-level execution with I/O redirection and a minimal Geatpy `Problem` test double. It did not reproduce the full stochastic search or emulate framework operators.

## Archived option table

[`case_study.json`](../data/case_study.json) preserves seven reported options, including inconsistencies:

| Option | Total (CNY) | Time (h) | Emissions (kg) | Carbon included? |
| --- | ---: | ---: | ---: | --- |
| Economic | 10,118.64 | 61.27 | 3,080.90 | No |
| Combined | 10,272.69 | 61.27 | 3,080.90 | Yes |
| Emission-constrained | 11,357.60 | 63.50 | 2,462.90 | Yes |
| Road only | 31,196.47 | 21.19 | 12,034.50 | Yes |
| Rail only | 20,506.01 | 22.43 | 5,653.20 | Yes |
| Water only | 58,920.86 | 79.03 | 2,845.20 | Yes |
| Reference multimodal | 27,938.92 | 37.00 | 8,827.91 | Yes |

The emission-constrained route is 10.56% more expensive and 20.06% lower-emitting than the combined route, and arrives 1.50 hours after the 62-hour target. These are archived simulation figures, not deployed savings.

## Transparent scale benchmark

[`synthetic_23city_100k_orders_30seeds.json`](../benchmarks/synthetic_23city_100k_orders_30seeds.json) records a reproducible benchmark on Python 3.13/macOS ARM. It generated and validated 100,000 **synthetic calibrated** orders, consolidated them into 16,327 compatible batches, and built a 23-node/754-edge synthetic network matching the historical mode-availability counts. The routing ablation benchmarks one network scenario, not all 16,327 batches.

All four native-GA variants used 20 individuals × 40 generations = 800 candidate evaluations for each of 30 seeds:

| Variant | Mean objective (CNY) | Median | Std. dev. | Restarts |
| --- | ---: | ---: | ---: | ---: |
| fixed baseline | 22,007.55 | 21,780.76 | 2,892.23 | 0 |
| adaptive only | 20,910.02 | 20,687.15 | 2,391.03 | 0 |
| catastrophe only | 20,042.21 | 19,760.54 | 2,958.83 | 29 |
| adaptive + catastrophe | 20,389.43 | 20,260.09 | 2,190.01 | 25 |

On this defined synthetic benchmark, the combined variant reduced mean objective by 7.35%, median objective by 6.98% and objective standard deviation by 24.28% relative to the fixed baseline. Catastrophe-only reached a lower mean than the combined variant in this sample, while the combined variant had the lowest dispersion; no variant is claimed to dominate generally. This is a controlled synthetic experiment, not the historical 23% claim, not a production latency result and not evidence about real enterprise orders.

## Real-Geatpy ablation and visualizations

A separate 150-run experiment uses the official Geatpy 2.7.0 wheel on one explicitly synthetic 23-city/754-edge network. Across 30 paired seeds, the adaptive-plus-catastrophe variant improved the objective by 11.46% on average relative to fixed operators, with 819 versus 800 candidate evaluations. A graph-heuristic-seeded hybrid retained a substantially better deterministic starting route, but the GA did not improve that seed; the benefit must therefore be attributed to the hybrid initialization rather than to genetic operators alone. Full assumptions and limitations are in [`geatpy-results.md`](geatpy-results.md).

## Historical multi-generation runs and saved configuration

The recovered `main.py` currently stores 100,000 individuals and `MAXGEN=1`; that single parameter state would stop after initial evaluation. It does not define what the code could do or what was run in 2022. Two saved logs end at generation index99 with 100,000 reported evaluations, and the defense document reports 100 rounds and embeds the matching trace plot. These artifacts confirm complete multi-generation runs under other saved-at-the-time parameters or revisions.

No seed is recorded and intermediate city IDs depend on Python set order. Exact reruns are consequently not deterministic from the available record, even though the historical runs themselves are evidenced.

## Evidence-calibrated corridor sensitivity

The checked-in [operator-calibrated corridor experiment](../benchmarks/real-case-sensitivity/README.md) evaluates 1,188 deterministic combinations of twelve deadlines, eleven carbon shadow prices, three payload assumptions and three time cases. At the 15-tonne/central setting, deadlines below 57.5 hours are infeasible; rail is selected from 60 through 192 hours, express water at 204/216 hours and regular water from 240 hours. Road becomes feasible at the assumed 96-hour central time but is dominated by rail in both price and modeled emissions. Observed-market carbon-price references do not change those selections; rail returns only near the explicitly labelled CNY 5,000-6,000/tCO2 structural stress range.

The corridor rerun uses 1,733 km for the explicit Chongqing-Shanghai rail row. The earlier 1,754 km value was the rail-column maximum from Chongqing to Zhangjiagang, not Shanghai. This correction slightly changes rail emissions and carbon costs but not the reported route sequence.

The portfolio grid applies the historical progressive schedule once to cumulative emissions. At 250 15-tonne water shipments, 179,925 kg crosses the 150,000 kg bracket and costs CNY 10,492.50, compared with CNY 8,996.25 if the first bracket were incorrectly reset on every shipment.

The selected 15-scenario algorithm experiment contains 2,250 dependency-free runs: five methods, 30 seeds and 400 GA candidate evaluations per run. The hybrid reports an additional mean 127.73 cost-time label expansions. Its median gap from the best observed route in each scenario is 0%, compared with 27.59% fixed, 23.94% adaptive, 15.82% catastrophe and 14.33% combined. This is an operator-calibrated-parameter/synthetic-topology search experiment, not historical competition performance and not an optimality certificate.

## Facility-network inventory

The generated [facility inventory](../benchmarks/facility-network/README.md) contains 20 candidates, including 15 resolved facilities, eight core candidates, twelve published service records and five intermodal-capability records. Thirteen facilities are supported as operational in both the historical and current snapshots. The raw evidence inventory still has zero optimizer-eligible service edges and transfers because no single public record supplies every numeric field required by the model. This blocks false precision while preserving a concrete collection queue for the Guoyuan-Waigaoqiao/Yangshan, Wuhu-Shanghai, Longtan-Yangshan, Luchaogang-Yangshan and Chuanshan corridors.

The [schematic](../benchmarks/facility-network/facility-network.svg) visualizes facility decisions and published service evidence. Dashed lines are not a complete transport graph and are not used in the 1,188-cell end-to-end lane sensitivity experiment.

## Facility-calibrated numeric case

A separate [1,260-cell facility experiment](../benchmarks/facility-case-analysis/README.md) combines operator disclosures, official market indices, a public spot observation, team-collected distances and explicitly labelled assumptions. It does not change the raw registry's evidence status. The central 15-tonne case admits four routes: road direct (96 h, CNY 15,000, 1,932.30 kg), rail plus Luchaogang-Yangshan road drayage (64.75 h, CNY 4,830 including transfer, 131.205 kg), bundled express water (204 h, CNY 1,400, 719.70 kg) and bundled regular water (240 h, CNY 1,130, 719.70 kg). The one-hour handling component now follows a published greater-than-60-percent completion threshold; the 1/4/8-hour scheduled-wait band remains an assumption.

The central feasible sequence is rail-road from 64.75 hours, express water from 204 hours and regular water from 240 hours; the direct road option is already dominated when it becomes feasible at 96 hours. At the 62.36/97.49 CNY/tCO2e reference prices, carbon cost is too small to change the selection. Rail-road beats express water above approximately 5,828 CNY/tCO2e and regular water above approximately 6,287 CNY/tCO2e in the central 15-tonne model. Those values are structural stress thresholds, not forecast carbon taxes. The result also shows that under the selected official default factors rail, not water, has the lowest modelled emissions.

## Globally coupled order allocation

The [facility allocation experiment](../benchmarks/global-order-allocation/README.md) assigns twelve modelled orders (239 tonnes) against eight timed capacity resources. A four-order subset is exhaustively evaluated over 3,072 candidate combinations. On the full twelve-order case, greedy and most 30-seed GA runs reach the same CNY 68,449.24 best-known value. This is an important negative result: adding a chromosome does not make GA necessary on a tiny, easily separable instance.

The separate [23-city allocation stress test](../benchmarks/synthetic-global-allocation/README.md) uses 48 synthetic orders, 2,055 tonnes, 23 OD pairs, 145 synthetic edges and 96 synthetic planning-horizon capacity resources. All 150 formal GA runs are feasible under 100 individuals × 150 generations. After selecting the controller on seeds 30--39 and validating it on untouched seeds 40--69, the formal 0--29 run has a CNY 372,578.33 deadline-greedy baseline and a CNY 304,051.85 best observed hybrid run: 18.39% below greedy when savings use greedy as denominator (equivalently, greedy is 22.54% above the best-known result). The hybrid has the lowest mean and standard deviation; combined has a CNY 34.72 lower median, so no method wins every statistic. A five-order candidate subset is exhaustively solved over 7,776 assignments, but the 48-order result has no global-optimality certificate.

The held-out paired validation gives selected hybrid 23 wins and 7 losses against legacy hybrid, with a mean change of -CNY 6,414.15 and an approximate 95% interval of [-9,333.41, -3,494.89]. This is evidence for one fixed synthetic instance, not universal superiority. The experiment demonstrates why joint capacity allocation can reward population search; it does not demonstrate enterprise-scale data, real carrier capacity, production benefit or historical 2022 performance. Full formulas and claim boundaries are in [`global-order-allocation.md`](global-order-allocation.md) and [`allocation-control-tuning.md`](allocation-control-tuning.md).

## Hard-cap corridor policy allocation

The checked-in policy experiment screens 108 demand, deadline, carbon-price and hard-cap cells, then compares five GA variants over 30 seeds in twelve selected scenarios. In the central 48-order/720-t balanced case, the best formal 20% allocation costs CNY 196,549.45 and emits 11,790.46 kg versus the frozen uncapped reference of CNY 182,555.44 and 14,929.10 kg. Rail-road allocation increases from 500 to 580 t while water falls from 220 to 140 t. Nine scenarios have a known feasible GA solution; no tested method finds one in three capacity/time stress cases. See [`corridor-sensitivity-results.md`](corridor-sensitivity-results.md).

## Preserved inconsistencies and defects

- The economic and combined totals differ from their displayed component sums by one cent; the reference multimodal total differs by one cent in the other direction.
- Reference emissions components sum to 8,822.06 kg, not the reported 8,827.91 kg.
- The road-only time breakdown contains an extra five-hour component not reconciled with its total.
- The map labels Anqing → Shanghai rail as 487 km, while the matching distance workbook stores 96 km.
- Carbon pricing raises `IndexError` at the second and higher brackets because `Yk[-1]` is read before any value is appended in those branches.
- The semifinal plot labelled average/best objective does not establish the captioned 23% speed improvement. No matched timing benchmark was recovered.

These discrepancies are retained rather than normalized to a preferred narrative.

## Optimality and verification meaning

The recovered results are best candidates from finite GA runs. They have no lower bound, exhaustive comparison or convergence certificate and must be called heuristic results, not proven global optima.

`tools/audit_results.py` checks transcribed arithmetic. `tests/test_historical_snapshot.py` checks snapshot hashes, saved configuration, the independent 100-generation log summaries, the combined-case calculation and the carbon defect. Extension tests cover four GA variants, equal candidate budgets, the 23-city/754-edge generator, order consolidation, capacity, closures and computed maps. Passing them proves those defined properties only; it does not recreate the unknown historical random state.
