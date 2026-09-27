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
