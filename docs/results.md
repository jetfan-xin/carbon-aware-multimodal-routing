# Results, comparisons and validation

## What the numbers represent

[case_study.json](../data/case_study.json) transcribes seven options from the final comparison notes. It preserves the reported values, including inconsistencies. The main example is a 100-tonne shipment from Chongqing to Shanghai with a 62-hour delivery window.

| Option | Reported total (CNY) | Time (h) | Emissions (kg) | Carbon cost included? |
| --- | ---: | ---: | ---: | --- |
| Economic | 10,118.64 | 61.27 | 3,080.90 | No |
| Combined | 10,272.69 | 61.27 | 3,080.90 | Yes |
| Emission-constrained | 11,357.60 | 63.50 | 2,462.90 | Yes |
| Road only | 31,196.47 | 21.19 | 12,034.50 | Yes |
| Rail only | 20,506.01 | 22.43 | 5,653.20 | Yes |
| Water only | 58,920.86 | 79.03 | 2,845.20 | Yes |
| Reference multimodal | 27,938.92 | 37.00 | 8,827.91 | Yes |

The baseline's route-selection procedure was not recovered. This table is an archived scenario comparison, not a controlled production benchmark.

## The defensible trade-off

Compare the emission-constrained option with the combined-cost option using the same total-cost definition:

```text
Cost increase = (11,357.60 / 10,272.69 - 1) × 100 = 10.56%
Emission reduction = (1 - 2,462.90 / 3,080.90) × 100 = 20.06%
Late arrival = 63.50 - 62.00 = 1.50 hours
```

The late-arrival penalty is 4,500 CNY in the source. With a 30 CNY/(tonne-hour) coefficient, 100 tonnes and 1.5 hours of delay, that penalty is internally consistent.

This makes a useful engineering conclusion: an emissions constraint can change the mode mix, but the result must be assessed together with the deadline and its penalty. It is not a free reduction in emissions.

## Corrections to presentation-level claims

- The final presentation's "about 5%" cost increase is not supported by its displayed totals. The comparison notes also mention 9.55%; recomputing the actual two totals gives 10.56%.
- The source notes mention a 20.02% emissions reduction; their displayed quantities give 20.06%.
- The "64% cost saving" calculation uses the economic total against a carbon-inclusive reference. A consistent combined-total comparison gives about 63.23%, but still has an unrecovered baseline and should not be used as a validated performance claim.
- The semifinal slide claiming a 23% search-speed improvement contains a plot whose legend says **Average Objective Value** and **Best Objective Value**. That plot is not itself a comparison between two algorithms. No matched timing benchmark was recovered.
- Claimed large-scale industry savings, government adoption and commercial operating benefits are projections from the presentation, not measured outcomes.

## Accounting discrepancies retained by the auditor

The economic and combined totals are each 0.01 CNY below their component sums; the reference multimodal total is 0.01 CNY above its component sum. These are recorded as cent-level differences rather than silently overwritten.

The reference multimodal emissions are more substantially inconsistent: 8,817.82 + 4.24 = 8,822.06 kg, not the reported 8,827.91 kg. The difference is 5.85 kg. The road-only time breakdown also includes an extra five-hour component that does not reconcile with its stated total.

## Other preserved runs

[terminal_summaries.json](../data/terminal_summaries.json) records three separate log variants. Two report 100,000 objective evaluations; another reports 20,000 and ends with an appended objective different from the final optimization block.

These variants are not averaged or pooled with the presentation case. Folder labels, printed durations and parameter snapshots are insufficient to recover their exact configurations. In particular, an "under 28" folder contains a printed duration of 40.08 hours.

## Verification utility

`tools/audit_results.py` uses decimal arithmetic to check component sums, cost-definition consistency, timing and comparison percentages. The unit tests deliberately assert that known discrepancies are detected. Passing tests means the transcription-audit logic works; it does not mean the historical solver or every original reported claim has been validated.
