# Carbon-Aware Multimodal Freight Routing

Route-planning research for freight journeys that combine road, rail and inland water transport, balancing delivery cost, arrival time and carbon emissions.

**2022 team project | Third Prize, Shanghai Open Data Innovative Application Competition | Yangtze River corridor case study**

I worked on greener route planning and the algorithm layer of a team-designed multimodal freight information platform. The project brought together transport-network data, operational assumptions and evolutionary optimization to examine when changing transport modes is worth the additional transfer time and cost.

This repository presents the project in English, with traceable historical results, an offline results auditor, and a runnable **2026 reconstruction of the route optimizer**. The competition's acronym, SODA, identifies the event, not the software.

## The engineering problem

The cheapest transport leg is not necessarily part of the cheapest feasible journey. Inland water transport can reduce operating cost and emissions, but transfers and late delivery can outweigh those savings. The model therefore considered:

- Transport and mode-transfer costs.
- Travel and transfer time, with delivery-window penalties.
- Transport and transfer emissions, converted into a carbon cost.
- Alternative demand scenarios and route choices across a 23-city study network.

The historical approach used Python/Geatpy, priority-based route encoding, and an adaptive genetic-algorithm design with diversity-restoring restarts. Data preparation was described using Pandas; saved map exports use Folium/Leaflet. See [method and implementation evidence](docs/method.md).

## A concrete result

The final presentation examined a **100-tonne shipment from Chongqing to Shanghai with a 62-hour delivery window**. Its two illustrated options show the actual trade-off:

| Reported option | Route | Total cost (CNY) | Time (h) | Emissions (kg) |
| --- | --- | ---: | ---: | ---: |
| Combined-cost option | Chongqing → Jiujiang → Anqing → Shanghai; water, rail, rail | 10,272.69 | 61.27 | 3,080.90 |
| Emission-constrained option | Chongqing → Anqing → Shanghai; water, rail | 11,357.60 | 63.50 | 2,462.90 |

Recalculating these reported totals gives **20.06% lower emissions at 10.56% higher cost**, with arrival **1.50 hours after the deadline** for the second option. These are archived simulation figures, not measured savings from a deployed logistics service. They do not establish global optimality. [Result definitions and caveats](docs/results.md)

## Explore the repository

- [Project brief](docs/project.md): context, contribution and the wider platform concept.
- [Technical method](docs/method.md): objectives, route encoding and what the surviving code actually shows.
- [Data sources](docs/data.md): observed inputs versus simulated assumptions, units and dataset inventory.
- [Results and validation](docs/results.md): consistent comparisons and discrepancies in the historical material.
- [Source recovery](docs/source-recovery.md): archive inspection, third-party code and the missing-source boundary.
- [Historical code screenshots](evidence/README.md): original implementation fragments with English explanations.
- [Runnable reconstruction](docs/reconstruction.md): Geatpy integration, input schema, modelling decisions and validation.

## Run the reconstructed optimizer

The new implementation provides directed road/rail/water routing, transfer accounting, progressive carbon pricing, soft or hard deadlines, scenario costs, adaptive genetic search and elite-preserving restarts. It includes a small synthetic network and an exhaustive baseline for correctness checks.

```bash
# No dependencies: enumerate the synthetic network exactly.
python3 -m routing examples/synthetic-network.json --solver exact

# In the documented Linux x86_64 / Python 3.10 environment:
python -m pip install --no-cache-dir -r requirements-geatpy.txt
python -m routing examples/synthetic-network.json --solver geatpy --seed 42
```

The synthetic example's exact minimum is **5,586.912 CNY expected cost**, using three water legs. This is a test fixture, not a competition result. The Geatpy integration is tested separately from the dependency-free cost model in [GitHub Actions](https://github.com/jetfan-xin/carbon-aware-multimodal-routing/actions/workflows/tests.yml). See the [reconstruction guide](docs/reconstruction.md) before supplying your own data.

## Run the offline audit

Python 3.10 or newer; no third-party packages, credentials or network access required.

```bash
python3 tools/audit_results.py
python3 tools/verify_repository.py
python3 -m unittest discover -s tests -v
```

The auditor checks the archived cost components, emission components, delivery constraints and comparison arithmetic. It intentionally reports inconsistencies rather than silently rewriting the historical numbers.

**Reproducibility boundary:** the complete custom 2022 Python/Geatpy solver was not recovered from the supplied archive. The executable tools and optimizer here were added in 2026. The optimizer implements a documented interpretation of the preserved model, not a byte-for-byte recovery or numerical reproduction of the historical runs. No blockchain backend, production deployment or live data-collection service is included.

## Recognition and provenance

The team, Zhuiguang, received Third Prize in the 2022 competition. The certificate was inspected during this repository's preparation. The original entry proposed a blockchain-based multimodal transport information platform for the Yangtze River Delta; this repository uses a descriptive name for its routing component. The [official competition archive](https://soda.data.sh.gov.cn/reviews.html) is provided for reference, although its HTTPS certificate prevented a fresh API verification during this audit.

Read [rights and attribution](RIGHTS_AND_ATTRIBUTION.md) before reusing material. Source files on the original drive were read only. No credentials, participant records, browser profiles, downloaded papers or third-party source trees are distributed here.
