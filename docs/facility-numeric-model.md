# Facility-level numeric model

## Calibrated Chongqing--Yangshan alternatives

For a central 15-t/20-ft shipment and zero carbon price, the admitted alternatives are:

| Route | Time | Transport + transfer cost | Emissions |
| --- | ---: | ---: | ---: |
| Guoyuan --road--> Yangshan | 96.00 h | CNY 15,000 | 1,932.30 kg |
| Guoyuan --rail--> Luchaogang --road--> Yangshan | 64.75 h | CNY 4,830 | 131.205 kg |
| Guoyuan --express water service--> Yangshan | 204.00 h | CNY 1,400 | 719.70 kg |
| Guoyuan --regular water service--> Yangshan | 240.00 h | CNY 1,130 | 719.70 kg |

The rail-road time combines a 57.5 h historical same-corridor rail reference, 1.5 h modelled drayage, 1 h handling, 4 h assumed wait and 0.75 h transfer time. The CNY 200 drayage value is one public spot posting, not a contract mean. The CNY 180/TEU Shanghai support payment is reported separately and not deducted from customer cost.

Under the cited default mode factors, rail-road has the lowest model emissions; water is cheaper but not the lowest-emission option. Rail beats express and regular water only at carbon shadow prices of approximately CNY 5,828 and CNY 6,287/tCO2e respectively. Prices near CNY 62--97/tCO2e do not change the route choice. Values near CNY 6,000 are structural stress tests, not carbon-tax forecasts.

The corrected team-workbook Chongqing--Shanghai rail distance is 1,733 km; 1,754 km belongs to Chongqing--Zhangjiagang. The original workbook is not silently edited.

The 1,260-cell route sensitivity output and SVG figures are in [`benchmarks/facility-case-analysis`](../benchmarks/facility-case-analysis/). Exact enumeration proves the best option only within the four admitted routes.
