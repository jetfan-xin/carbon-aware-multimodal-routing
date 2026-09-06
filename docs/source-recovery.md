# Source recovery and reproducibility

Original project period: September-November 2022.

## Inspection performed

The supplied folder was inspected recursively, including the October code subdirectories, November routing folders, relevant ZIP archives, final presentation, semifinal PDF, Word defense notes, input workbooks, generated maps and terminal output. Original files were read only. Browser-profile folders, downloaded research datasets and unrelated early topics were not copied into this repository.

The final 30-slide presentation and 34-page semifinal PDF were read in full at the text level. The code screenshots and selected technical slides were also inspected visually. The award certificate was visually checked. Spreadsheet inspection distinguished populated cells from stored/formatted dimensions.

## October code directories

| Directory | Finding | Treatment |
| --- | --- | --- |
| `multimodal-transportation-optimization-master` | Ken Huang's mathematical-programming project; the local Python file has the same executable logic as the bundled reference, with header/whitespace differences | Reference only; not republished as original work |
| `MTRecS-DLT-master` | Published CNN/GBDT transportation recommender; source files match the bundled archive | Reference only |
| `Context-Aware-Multi-Modal-Transportation-Recommendation-master` | KDD Cup 2019 baseline; inspected code/docs match the archive | Reference only |
| `Path-optimization-of-uncertain-multimodal-transport-main` | MATLAB AFO/GA/PSO reference implementation; five algorithm/support files match the nested archive, while the local driver removes some configuration sections | Not the final custom Python/Geatpy solver; not republished |

The topic similarity of these repositories is not evidence that they are the final competition implementation.

## November code directories

The extracted Geatpy Python files were compared against the bundled `geatpy-master.zip`. The only byte differences found were two zero-byte files. No additional nonempty custom routing implementation was found in that comparison. Available compiled `MyProblem` caches identify ordinary Geatpy demonstration functions, not the routing model.

The standalone `GA.m` is a MATLAB driver that calls helper functions absent from that file's context. It is not a complete recovered solver, and its provenance is insufficient to present it as an original implementation here.

The Notion HTML inside the November reference ZIP contains tutorial links and planning notes, not the complete final source. The final code screenshots and terminal outputs remain valuable evidence of work, but do not fill these executable-source gaps.

## Evidence identifiers

The [source manifest](../source-manifest.json) assigns stable IDs to the inspected project-specific sources and records SHA-256 hashes. Full local paths are retained only in a private index outside the repository. Public result records refer to these IDs.

The two screenshots under `evidence/` are exact image assets from the final presentation, verified by byte comparison. Their original Chinese comments are retained as historical evidence; all newly written explanations are English.

## Included and excluded

Included: English project and technical documentation, compact parameter/result transcriptions, original code screenshots, provenance hashes, an offline arithmetic-audit utility, and a [runnable optimizer](implementation.md).

Excluded: downloaded third-party source trees, vendor binaries, full raw datasets, reference papers, certificates, personal contact details, browser profiles, old CDN-dependent HTML exports and credentials. No repository-wide reuse license is asserted for the team archive.

## Reproducibility status

The complete competition solver was not recovered. The executable optimizer was subsequently implemented from the preserved project materials, with explicit assumptions for missing details; it is not the archived competition source or a numerical reproduction of the historical runs. Modelling decisions and tests are documented in the [optimizer guide](implementation.md).

To extend the archive faithfully, add the missing custom Python modules with provenance, the matching network and configuration files, dependency versions, random seeds, and raw results for comparable baselines. Do not fill missing history by relabelling a third-party implementation.
