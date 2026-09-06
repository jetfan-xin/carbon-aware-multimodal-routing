# Data sources and input definitions

## Observations versus assumptions

The semifinal report and final defense notes identify three different evidence levels. They should not be merged into a single claim about "real data."

| Input | Source described in the project | Evidence retained |
| --- | --- | --- |
| Shanghai road details and freight totals | Competition/public-data platform | Dataset descriptions and selected workbook files |
| Intercity road, rail and water distances | Amap and project-assembled distance tables | Several versioned distance workbooks |
| Carbon-pricing background | World Bank material cited in defense notes | Background attribution; exact dataset-to-coefficient derivation not recovered |
| Order quantities, speed variation and some operational inputs | Simulated or assumed | Parameter workbooks and narrative definitions |
| Live GPS/RFID data, carrier orders and blockchain records | Proposed platform resource pool | Architecture descriptions, not recovered live collection logs |

Pandas-based missing-value handling and median-absolute-deviation outlier treatment are described in the semifinal report. Their complete processing scripts are not present in the supplied project implementation materials.

## Case-study network inventory

The principal November distance workbook contains **253 populated origin-destination pair rows plus one header**, involving **23 distinct city names**. It has 253 road distances, 250 rail distances and 251 water distances; three rail and two water entries use `#` to mark unavailable connections.

253 equals the number of unordered pairs among 23 cities. This is an inventory property, not proof of how directed edges were ultimately created by the missing loader. Whitespace in city labels must be normalized before matching.

The worksheet's stored dimensions extend beyond its populated rows. Counting the XML range or formatted rows would overstate this specific table's data count. Conversely, this small case-study table does not establish the total scale of data accessed during the wider project.

Other versions include road-only, rail-only, water-only, reduced-network, original and error-labelled workbooks. They are separate experimental inputs, not interchangeable copies of one canonical dataset.

## Parameter snapshot

[parameter_snapshot.json](../data/parameter_snapshot.json) transcribes the six small November parameter workbooks into English fields. Relevant source locations are:

| Source ID | Sheet / cells | Meaning |
| --- | --- | --- |
| parameters-transport | Sheet1, A1:F4 | Speeds, transport-rate bands and emission coefficients |
| parameters-transfer | Sheet1, A1:D4 | Pairwise mode-transfer time, emissions and cost |
| parameters-time-cost | Sheet1, A1:B2 | Storage and late-arrival cost coefficients |
| parameters-window | Sheet1, A1:B2 | Earliest/latest delivery time |
| parameters-carbon | Sheet1, A1:C5 | Historical carbon-cost brackets |
| parameters-demand | Sheet1, A1:C4 | Quantities and scenario probabilities |

Keep the units explicit: tonne-kilometres for transport coefficients, kilograms for emissions, hours for time and CNY for cost. Transfer time is stored as hours per 1,000 tonnes. The transport-rate workbook contains three bands but does not supply their boundaries.

These inputs do not fully reproduce the presentation. For example, the listed rail-water transfer rate implies 250 CNY at 100 tonnes, while the presentation case reports 500 CNY. The three-scenario mean quantity is 102.1 tonnes rather than 100 tonnes. These are version/configuration gaps, not values to "fix" silently.

## Scale claims

The earlier CV describes using millions of transport data points. The supplied archive did not yield a corresponding acquisition manifest, record-count log or API-call history. The project should therefore not present that quantity as independently verified by this repository. A solver's 100,000 objective evaluations are not 100,000 downloaded transport records or API calls.

## Publication boundary

The repository includes compact parameter and aggregate-result transcriptions, not the full competition datasets, raw mapping-provider exports, individual orders or operational tracking records. Original workbooks remain private and unchanged. The [source manifest](../source-manifest.json) records hashes and evidence identifiers for traceability without publishing personal local filesystem paths.
