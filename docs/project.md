# Project brief

## Context

This was a September-November 2022 student team project for the Shanghai Open Data Innovative Application Competition. The original entry proposed a multimodal freight information platform for the Yangtze River Delta. The team name was Zhuiguang; the inspected award certificate records Third Prize.

The English repository title describes the routing component. SODA is the competition acronym, not a project or product name. A precise overall top-ten ranking is not asserted here because the inspected certificate does not specify a ranking.

## Problem and users

Shippers need a route that meets delivery requirements without treating each transport leg independently. Carriers need advance information about handovers. A public-sector operator could benefit from aggregated transport and emissions information.

The team proposed a shared information layer and shipper/carrier interfaces. Within that larger concept, the routing work investigated how road, rail and inland water transport can be combined while accounting for transfers, time windows and carbon costs.

## My contribution

My focus was greener route planning and its algorithmic integration into the team platform concept. The project involved formulating transport choices as an optimization problem and evaluating the cost/time/emissions consequences of alternative routes.

The final presentation identifies Jingfan Xin as the team member from Renmin University's Gaoling School of Artificial Intelligence. Project records describe a Python/Geatpy implementation and retain code screenshots, route outputs and input workbooks. The complete custom solver source has not been recovered, so this repository does not assign unsupported line-by-line authorship or claim sole ownership of the team platform.

## What was demonstrated

- A 23-city case-study network with distances for three transport modes.
- A cost model that distinguishes transport, transfer, delivery-time and carbon components.
- Reported routing outputs for alternative objectives and transport-mode restrictions.
- Saved Folium/Leaflet route-map exports and interface designs.
- A competition presentation and award certificate.

## What remained a platform proposal

The documents also discuss order allocation, shipment tracking, consortium-blockchain data sharing, smart contracts, one-stop settlement and government dashboards. These belong to the broader design narrative. The inspected folder does not supply a deployable backend, smart-contract implementation, live sensor pipeline, or production-operating evidence for them.

The project is therefore presented as an optimization prototype and platform-design study, not as an operating government service or a commercial logistics deployment.

## Why the project is relevant

The transferable engineering work lies in turning operational constraints into a computable decision problem, combining heterogeneous data with explicit assumptions, selecting an optimization approach, and making its trade-offs understandable to non-specialist users. The central result is a decision trade-off, not an isolated percentage improvement.
