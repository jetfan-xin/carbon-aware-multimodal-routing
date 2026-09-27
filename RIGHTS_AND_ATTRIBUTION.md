# Rights and attribution

The historical project was team work by Zhuiguang for the 2022 Shanghai Open Data Innovative Application Competition. Jingfan Xin confirms that he wrote the project-specific 2022 routing code and designed the routing algorithm; one teammate shared the manual data-collection work. This does not imply ownership of the full team platform or of third-party dependencies.

The byte-exact files in `historical/GA_code` are preserved as project evidence. No repository-wide reuse licence is asserted for those team materials; contact the rights holders before redistribution or derivative use where permission is unclear.

## Third-party software and references

- [Geatpy](https://github.com/geatpy-dev/geatpy) 2.7.0 is the evolutionary-computation framework called by the historical code. Its `Problem`, population, SEGA template, selection, crossover, mutation, ranking, plotting and saving code are third-party and are not vendored here.
- Ken Huang's multimodal transportation optimization, MTRecS-DLT, KDD Cup baselines and Matlab AFO/GA/PSO repositories found in the source archive are external references, not recovered project implementation. They are not redistributed.
- Folium/Leaflet and external map/CDN services were used by saved map exports. The exports and third-party tiles are not published here.

## Current maintained implementation

`routing` and its tests were developed later, with AI assistance, from incomplete evidence and then extended after source recovery. Their input validation, backtracking decoder, scenario/risk model, hard constraints, current adaptive formula, equal-budget native GA, deterministic seed handling, synthetic data generator, batch pipeline and exact/state-Dijkstra baselines are later additions. This separation does not deny the adaptive/catastrophe implementation described in the 2022 defense; it prevents the new formulas from being backdated as the exact historical source.

## Documents and data

The public repository contains small English transcriptions of project-specific parameters and aggregate simulation results, selected full-page renders from the semifinal and final team presentations, and two code screenshots embedded in the final presentation. The selected pages exclude team photographs, biographies and contact details. Original papers, certificates, source workbooks, complete competition submissions, complete competition data and mapping-provider datasets are not uploaded. Provenance hashes identify the reviewed evidence without exposing the maintainer's local filesystem paths.

The verification utilities, routing implementation, synthetic fixture, Geatpy integration and tests were developed with AI assistance. See [implementation provenance](docs/source-recovery.md). The integration calls Geatpy as a separately installed dependency; its source and compiled libraries are not vendored.

Downloaded source trees, browser files, credentials and other private records are also excluded. Full local evidence paths remain only in a private index outside the public repository.
