# Project brief

## Context

This was a September-November 2022 student team project for the Shanghai Open Data Innovative Application Competition. The team, Zhuiguang, received Third Prize. The English repository title describes the routing component; SODA is the competition acronym, not the software name.

The wider proposal combined shipper/carrier interfaces, multimodal routing and an information-sharing architecture. The recovered executable scope is narrower: one Chongqing-Shanghai shipment over a 23-city road/rail/water network with cost, time and carbon accounting.

## Competition progression

The project passed through three successive competition gates:

1. **Preliminary round:** the initial problem, data and feasibility proposal advanced.
2. **Semifinal:** the team submitted a 34-page technical report with the data-processing plan, route-optimization method, prototype and preliminary model outputs, then advanced again.
3. **Final:** the team presented and defended a 30-slide final deck with a more detailed case calculation, receiving Third Prize.

Selected non-personal pages from the semifinal and final materials are published in the [evidence gallery](../evidence/README.md). Early working decks and the full competition submissions remain in the private archive; this avoids exposing team biographies and redistributing unnecessary material while still making the progression and technical work inspectable.

## Problem and users

The intended users were freight shippers, carriers and public-sector stakeholders comparing multimodal routing alternatives.

## Contribution boundary

Jingfan Xin confirms that he wrote the 2022 project-specific code and designed the routing algorithm; one teammate shared the manual data-collection work. This supports first-person ownership of the routing and quantitative-analysis workflow, but not of the whole team platform.

Geatpy's SEGA template, selection, crossover and mutation operators are third-party framework code. Downloaded reference repositories and Matlab examples found in the archive are also not personal implementations.

## Demonstrated by code and data

- A 23-city, three-mode expanded graph loaded from Excel.
- A 69-integer priority chromosome and greedy route decoder.
- A single cost objective combining distance-banded transport, transfer, time-window and carbon costs.
- Historical route/cost/time/emissions output and a separate Folium map script.
- Saved 100-generation runs with 100,000 reported evaluations, trace plots and decoded routes.

The defense material documents adaptive operators and a 20-generation catastrophe condition as implemented work. The exact custom-controller source revision has not been matched to the byte-exact `GA_code` snapshot, so the public repository preserves both facts instead of using the snapshot's current `MAXGEN` value to deny the historical implementation. Scenario robustness, a hard emission constraint and multi-objective optimization still require separate code-level confirmation.

## Platform proposal boundary

Order allocation, live shipment tracking, consortium blockchain, smart contracts, one-stop settlement and government dashboards remain architecture/interface proposals. No deployable backend, chain code, sensor pipeline or production operating evidence was recovered.

The project should therefore be presented as a competition optimization prototype and platform-design study. Historical calculations are simulations, and the heuristic output is not a global-optimality certificate.
