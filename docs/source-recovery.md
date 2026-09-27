# Source recovery and reproducibility

Original project period: September-November 2022. Recovery audit: 27 September 2026.

## Recovered project implementation

The `GA_code` directory contains six Python files dated 23 November 2022 plus a 2026 recovery note. The six code files form a coherent call chain: `main.py`, `ga.py`, `input.py`, `utils.py`, `calculate.py` and the independent `map.py`. They are preserved byte-for-byte in [`historical/GA_code`](../historical/GA_code), with file identities in [`historical/FILE_MANIFEST.json`](../historical/FILE_MANIFEST.json).

The 2026 note says that all code, but no example data, is present. This supports treating the directory as the recovered project-specific code set. It does not prove that every development revision, test, dependency or configuration from 2022 survives.

Seven referenced workbooks and the coordinate workbook were located elsewhere in the source archive and matched by exact filename and content. They were inspected from temporary copies and are identified by SHA-256, but are not published here. Public manifests contain stable source IDs only; private absolute paths stay in an external private index.

## Read-only inspection

The source directory was recursively inventoried without running code or creating files there. Static inspection covered Python, Matlab, notebooks/configuration, text, Office/PDF documents, spreadsheets, images, HTML, logs, archives, caches and bundled package source. Execution, workbook parsing and rendering used temporary copies.

The final presentation, semifinal report, defense notes, code screenshots, selected saved maps and terminal outputs were compared against the recovered code. Spreadsheet inspection distinguished populated cells from stored/formatted dimensions.

## External and third-party material

The surrounding archive contains downloaded multimodal-optimization, recommendation and Matlab reference projects, plus a Geatpy source tree/archive. Those are reference or framework code, not Jingfan Xin's personal implementation and are not republished.

The adjacent Geatpy source identifies version 2.7.0. Its SEGA template and operators explain the framework defaults, but those framework implementations remain third-party. The recovered project code only configures and calls them.

## Earlier document-derived implementation

Before `GA_code` was found, a runnable optimizer was built from screenshots and documents at commit `329d84ea50ed9b19169d410f596266c333531f12`; its last pre-recovery baseline was `2f3551f4db70f79ca39471f2226676686c1caad8`. Its tested successor is now maintained under [`routing`](../routing).

That implementation added a backtracking decoder, input validation, expected/worst scenario objectives, hard constraints, a new adaptive formula, elite-preserving restarts, fixed seeds and an exact small-network baseline. The current maintained version also includes equal-budget native-GA ablations, historical rate bands, capacity/edge-state handling, order consolidation, synthetic scale generation and computed SVG maps. These are later engineering additions, not silently backdated historical behavior. The detailed comparison is in [`ORIGINAL_VS_CURRENT_CN.md`](ORIGINAL_VS_CURRENT_CN.md).

## Reproducibility status

**Recovered:** project-specific source; exact file hashes; the matching network and parameter workbook identities; the Geatpy framework version; static call graph; the combined-case cost path; historical defects.

**Not recovered or not confirmed:** exact Python/NumPy/Pandas/Folium versions; a lock file; random seed/state; a portable Geatpy 2.7.0 build for the current platform; the complete settings behind every terminal log; the exact source revision containing the defense-documented adaptive/catastrophe controller; executable robust-scenario logic matching the presentation.

The full entry point has therefore not been reproduced byte-for-byte in its historical environment. A controlled probe called the unchanged decoder and cost functions after I/O redirection; it did not emulate Geatpy. This is a present-day reproduction boundary, not evidence that the 2022 multi-generation runs did not occur. The guarded compatibility runner refuses silent framework substitution.

The correct conclusion is not “the complete solver is still missing.” The project-specific final `GA_code` is recovered, but the complete historical *execution environment and every recorded experiment* are not.

## Public inclusion boundary

Included: exact project-code snapshot, manifests, documentation, compatibility wrapper, compact English parameter/result transcriptions, two presentation screenshots and offline verification utilities.

Excluded: Geatpy/framework source, downloaded reference repositories, raw workbooks, papers, certificates, browser profiles, credentials, personal data and obsolete third-party HTML assets. No repository-wide licence is asserted for the historical team files.
