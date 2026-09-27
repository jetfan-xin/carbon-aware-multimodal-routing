# Recovered historical implementation

`GA_code/` is a byte-for-byte snapshot of the recovered project-specific files. The six Python files have 2022-11-23 modification times in the evidence source. `GA_code/readme.txt` is a 2026 recovery note saying that the folder contains all code but no example data; it is not treated as 2022 source code.

The snapshot is intentionally not reformatted, renamed internally, or patched. Its original Windows paths, CRLF line endings, comments, bugs and output behavior are evidence. Do not modernize files in place. Use a separate compatibility layer for path redirection or environment work.

The snapshot does not include Geatpy, downloaded reference projects or raw workbooks. Geatpy is third-party software. Workbook identities and hashes are listed in `FILE_MANIFEST.json`; the original local paths remain in the private source index outside this repository.

The executable entry point is `GA_code/main.py`. Its retained defaults are 100,000 individuals and `MAXGEN=1`; that particular setting stops after initial evaluation, but `MAXGEN` is a mutable experiment parameter and the Geatpy template contains the full evolutionary loop. Separate 2022 artifacts record 100-generation runs with 100,000 evaluations. See the Chinese analysis and implementation guide for the distinction between a saved configuration, algorithm capability and historical execution.
