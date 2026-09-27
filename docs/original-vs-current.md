# Original 2022 implementation versus the maintained system

The original implementation is the byte-exact project code in [`historical/GA_code`](../historical/GA_code/). The maintained system is the tested package under [`routing`](../routing/). Both are authored project work at different times, but later engineering additions must not be backdated to the competition.

| Dimension | Recovered 2022 code | Maintained system |
| --- | --- | --- |
| Primary task | One 100-t Chongqing--Shanghai route | Single-route analysis plus globally coupled multi-order allocation |
| Network | 23 cities expanded to 69 mode nodes | Explicit directed mode edges; facility-specific transfers; synthetic 23-city stress graph |
| Chromosome | 69 integer node priorities | Route solver: edge priorities; allocation solver: one candidate-choice integer per order |
| Decoder | Greedy maximum-priority next node | Cycle-safe route enumeration/beam search, then portfolio allocation |
| Objective | Transport + transfer + time-window + carbon cost | Same core components plus scheduled waiting, aggregate carbon brackets and optional hard portfolio emissions cap |
| Demand uncertainty | Workbook scenarios loaded but unused | Explicit route-model scenarios; deterministic portfolio scenarios clearly labelled |
| Constraints | `CV` remains zero; time and carbon are soft costs | Deadlines, shared capacity and emissions cap evaluated explicitly with feasibility-first ranking |
| Selection/crossover/mutation | Geatpy SEGA framework | Geatpy route integration plus dependency-free fixed/adaptive/catastrophe allocation variants |
| Adaptive mechanism | Claimed by archived presentation; exact controller source missing | Genotype-diversity and stagnation formula in repository code |
| Catastrophe | Historical document says random injection after 20 unchanged generations; source missing | Auditable 25% partial restart after configured patience |
| Elitism | Geatpy template behavior | Explicit parent--offspring merge and elite retention |
| Data | Team-collected case inputs; not enterprise orders | Field-calibrated public evidence plus explicitly synthetic/modelled orders |
| Validation | Archived route, trace and terminal artifacts | Unit tests, exact small-instance oracles, 30-seed experiments and Docker Geatpy integration |
| Optimality | Heuristic | Exact only on named small candidate sets; otherwise heuristic best-known results |

Input validation, deterministic seeds, cycle-safe decoding, exact enumeration, state-Dijkstra, facility-specific transfer rules, global order allocation, shared capacity, hard emissions caps, synthetic generators, ablation experiments and automated SVG reports are maintained-system features. They are legitimate extensions of the same problem, but not evidence of the exact 2022 code.

A defensible explanation is: the 2022 project established the multimodal graph, priority encoding, decoder and four-part cost model in Python/Geatpy; the maintained project later made the workflow reproducible, added explicit capacity and emissions constraints, and evaluated it with controlled synthetic and corridor-calibrated experiments. It is not defensible to describe current synthetic orders as historical government records or to claim the later controller was present in the recovered snapshot.

See [the original-code analysis](original-ga-code-analysis.md) and the [integrated project report](PROJECT_REPORT.md).
