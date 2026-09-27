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

A separate 150-run experiment uses the official Geatpy 2.7.0 wheel on one explicitly synthetic 23-city/754-edge network. Across 30 paired seeds, the adaptive-plus-catastrophe variant improved the objective by 11.46% on average relative to fixed operators, with 819 versus 800 candidate evaluations. A graph-heuristic-seeded hybrid retained a substantially better deterministic starting route, but the GA did not improve that seed; the benefit must therefore be attributed to the hybrid initialization rather than to genetic operators alone. Full assumptions, component values, win/tie/loss counts, limitations and SVG figures are in [`GEATPY_RESULTS_ANALYSIS_CN.md`](GEATPY_RESULTS_ANALYSIS_CN.md).

## Historical multi-generation runs and saved configuration

The recovered `main.py` currently stores 100,000 individuals and `MAXGEN=1`; that single parameter state would stop after initial evaluation. It does not define what the code could do or what was run in 2022. Two saved logs end at generation index99 with 100,000 reported evaluations, and the defense document reports 100 rounds and embeds the matching trace plot. These artifacts confirm complete multi-generation runs under other saved-at-the-time parameters or revisions.

No seed is recorded and intermediate city IDs depend on Python set order. Exact reruns are consequently not deterministic from the available record, even though the historical runs themselves are evidenced.

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
