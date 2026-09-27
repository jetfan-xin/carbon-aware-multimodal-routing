# Data sources and loader behavior

## Referenced workbook set

The recovered loader requests seven Excel files by exact Chinese filename. The independent map script requests an eighth coordinate workbook. Identities, hashes, sheet names and stored ranges are in [`historical/FILE_MANIFEST.json`](../historical/FILE_MANIFEST.json).

| Source ID | Used by | Required columns / content |
| --- | --- | --- |
| `distance-network` | `input.get_distance`, `utils.city_index_map` | start, end, road/rail/water distance |
| `parameters-transport` | `input.get_tparg` | speed, three distance-band rates, emissions |
| `parameters-transfer` | `input.get_tsarg` | pairwise time, emissions, cost |
| `parameters-time-cost` | `input.get_timearg` | storage and delay rates |
| `parameters-carbon` | `input.get_carbon` | four thresholds and rates |
| `parameters-window` | `input.get_time` | earliest/latest hour |
| `parameters-demand` | `input.get_input` | quantity and probability for three scenarios |
| `transfer-coordinates` | `map.py` only | city, longitude, latitude |

All are on `Sheet1`; no formulas were found. The executable code uses Pandas `read_excel`; the historical Excel engine and exact Pandas version are unknown.

## Network table

The distance workbook has 253 populated pair rows plus its header and 23 distinct city names. This is exactly one row per unordered city pair. Road has 253 numeric entries, rail 250 plus three `#` markers, and water 251 plus two `#` markers.

The loader removes spaces from city names, creates IDs through an unordered Python set, and inserts only the direction shown in each row. It does not add reverse edges. The result is 253 road, 250 rail and 251 water directed edges across the three layers.

The coordinate workbook has 25 city rows, two more than the optimizer network. It belongs only to `map.py`; it is not evidence that the optimization graph has 25 cities.

The derived, non-row-level profile in [`historical_aggregate_profile.json`](../data/historical_aggregate_profile.json) also records distance distributions: road 30–1,695 km (median 464), rail 31–1,754 km (median 503), and water 18–2,399 km (median 609). These summaries can calibrate synthetic tests without redistributing mapping-provider rows.

## Parameter values used by GA_code

| Category | Values | Unit / interpretation |
| --- | --- | --- |
| speed | road 80, rail 60, water 30 | km/h |
| road rates | 0.263, 0.2485, 0.1805 | CNY/(km·t), bands <500, <1000, otherwise |
| rail rates | 0.196, 0.170, 0.1365 | CNY/(km·t), same bands |
| water rates | 0.045, 0.0365, 0.0255 | CNY/(km·t), same bands |
| transport emissions | 0.071, 0.042, 0.012 | kg/(km·t), road/rail/water |
| transfer time | 50, 50, 50 | h/1000 t, road-rail/road-water/rail-water |
| transfer emissions | 0.128, 0.117, 0.113 | kg/t |
| transfer cost | 2, 2.25, 2.5 | CNY/t; historical cost function doubles counts |
| time penalties | 15 early, 30 late | CNY/(h·t) |
| window | 0 to 62 | hours |
| carbon schedule | thresholds 0, 150k, 500k, 1m; rates .05, .10, .15, .20 | kg and CNY/kg |
| scenarios | (150,.36), (85,.50), (40,.14) | tonnes and probability; loaded but unused |

The fixed optimizer quantity is 100 tonnes. The scenario probabilities sum to one and imply 102.1 tonnes, but that expectation is never computed by `GA_code`.

## Version sensitivity

Older workbooks elsewhere in the archive are not interchangeable: an earlier set contains approximately doubled transport rates, transfer costs 8/9/10, a 55-65 hour window and a first carbon threshold of 100,000 kg. The recovered code filenames alone do not distinguish versions; the source manifest hashes do.

The published [`parameter_snapshot.json`](../data/parameter_snapshot.json) is an English transcription for audit purposes, not a replacement input accepted by the original loader.

## Evidence levels and publication boundary

Some project materials mention public-platform freight data, mapping-provider distances, simulation, GPS/RFID, live orders and blockchain records. The recovered optimizer directly reads only the eight workbooks above. It contains no acquisition pipeline, live tracking feed, order database or blockchain implementation.

The repository does not publish the raw workbooks or mapping-provider exports. It publishes stable source IDs, file hashes and compact parameter/result transcriptions. Millions-of-records claims are not independently supported by a data manifest; objective evaluation counts must not be relabelled as collected records.

## Reproducible scale data

[`synthetic.py`](../routing/synthetic.py) produces transparent stress-test data. With its default seed and 23 nodes it generates all 253 forward city pairs and exactly 754 mode edges, matching the historical availability counts while inventing every row-level distance. It can also generate user-selected synthetic order counts.

Each order carries `source_type=synthetic_calibrated`. The full-flow validator rejects unknown provenance labels. Consequently “100,000 orders” in a benchmark means 100,000 reproducible synthetic rows processed by the maintained pipeline, not 100,000 historical or enterprise shipments.

The allocation experiments use two additional, separately labelled demand layers. [`cq_shanghai_facility_scenario.json`](../data/allocation_instances/cq_shanghai_facility_scenario.json) contains twelve modelled orders and eight scenario departure capacities for the facility-calibrated graph. The underlying lane values retain their field-level provenance, but the orders, departure phases and allocatable slots are not observed bookings or manifests. The 23-city allocation stress test generates all 48 orders and 96 planning-horizon rail/water capacities deterministically; those resources deliberately constrain a synthetic algorithm benchmark and are not carrier capacity statements.

## Evidence-calibrated corridor layer

[`real_world_benchmarks.json`](../data/real_world_benchmarks.json) adds a separate calibration layer. It records publisher, date, URL, unit, quotation scope and evidence class for every value. It does not overwrite the 2022 workbook snapshot.

The Chongqing-Shanghai case now distinguishes an operator-reported 15,000/4,600/1,400 CNY road/rail/water comparison, a 55–60 hour historical same-corridor train, the official 8–9 day express-water range, a current operator-reported ten-day/twice-weekly water service and the August 2025 official 1,130 CNY FIO average. The former unsupported ten-percent express surcharge and Chengdu-Shanghai rail-time proxy were removed. Road time, 10/15/20-tonne payloads, endpoint mappings and linear allocation to the synthetic 23-city topology remain explicit assumptions. The separate Chengdu-Shanghai record is retained only as an independent validation case.

The explicit Chongqing-Shanghai workbook row is road 1,695 km, rail 1,733 km and water 2,399 km. An earlier calibration used 1,754 km for rail by confusing the rail-column maximum (the Chongqing-Zhangjiagang row) with the Shanghai row. The calibration and regression test now use 1,733 km; the aggregate profile correctly retains 1,754 km as the maximum across all pairs.

[`carbon_price_scenarios.json`](../data/carbon_price_scenarios.json) distinguishes observed national-ETS reference prices from stress prices and the historical project brackets. These are shadow-price scenarios: the repository does not claim that freight transport currently pays a Chinese carbon tax. [`service_time_scenarios.json`](../data/service_time_scenarios.json) documents deadline meanings and which timing distributions are assumptions.

## Facility-level Yangtze Delta registry

[`data/facility_network`](../data/facility_network) separates candidate facilities, published service evidence and transfer capabilities. National/provincial plans create candidates only. A record becomes an optimizer edge only after exact endpoints, operational dates, distance, service time and the required comparable cost fields are present.

The inventory contains 20 candidates: 15 resolved facilities and five unresolved port/city gateways. Eight are core general-container candidates. Historical Yangpu station and Chongqing Tuanjiecun are retained as evidence-only facilities, not silently substituted for current Guoyuan/Luchaogang endpoints. Wuhu Zhujiangqiao is kept separate from the coal-oriented Yuxikou area; Shanghai Waigaoqiao, Luchaogang railway centre and Yangshan are three facilities; and the 2026 Nantong Tonghai record is excluded from the historical snapshot.

The registry currently records twelve published service facts and five transfer-capability facts but deliberately exposes zero raw optimizer edges and zero raw transfers. That is a data-completeness result, not a claim that the services do not exist. New records capture the historical Yangpu–Tuanjiecun train, a 2021 official Chongqing-to-Luchaogang endpoint statement, the current Chongqing–Shanghai water operator disclosure and one sanitized Luchaogang-area spot drayage posting. No single record supplies a consistent combination of exact current terminals, distance, full tariff scope, schedule time and handling data.

[`operational_evidence_gaps.json`](../data/operational_evidence_gaps.json) is the field-level negative-evidence ledger. It retains public partial observations alongside the still-missing enterprise fields, so a public rate index, procurement profile or policy subsidy cannot be mistaken for a completed customer order or contract.

[`model_inputs.json`](../data/facility_network/model_inputs.json) is a separate calibrated-analysis layer, not a promotion of those raw records. It contains seven edges, one facility-specific transfer and three runnable cases. Every numeric field carries an evidence class and source IDs. The Luchaogang-area drayage now uses a single public CNY 200 spot observation and a reported 45 km route distance, while handling/waiting times, endpoint mappings and some time bands remain assumptions. The Guoyuan-Yangshan case admits direct road, bundled express/regular water and a true two-leg rail-road structure through Luchaogang. Wuhu and Nanjing feeder calibrations remain independent current-reference cases rather than invented intermediate calls for Chongqing freight.

## Policy-allocation design data

[`policy_experiment.json`](../data/policy_experiment.json) defines three deterministic demand sizes, three deadline profiles, three carbon shadow prices, four hard emissions targets and three planning-horizon capacity resources. Every order and capacity value is an experiment assumption. The 9.5%, 20% and 30% percentages have linked policy anchors but are not represented as direct legal shipment caps. Facility prices, times, distances and mode factors continue to come from the separately classified facility model.
