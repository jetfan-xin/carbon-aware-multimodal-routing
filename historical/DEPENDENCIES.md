# Historical dependency evidence

The recovered code imports `numpy`, `pandas`, `geatpy` and `folium`. `pandas.read_excel()` also needs an XLSX engine; `openpyxl` is the compatible modern choice, but the exact 2022 engine and version were not recorded.

The adjacent archived Geatpy source identifies itself as 2.7.0 and declares `numpy>=1.17.0` and `matplotlib>=3.0.0`. Its bundled native modules are for 64-bit Windows and Linux CPython 3.6. The final presentation names Windows 10 x64 and PyCharm but does not state the Python, NumPy, Pandas, Folium or Matplotlib versions. CPython 3.6 is therefore a strong environment clue, not a confirmed version claim.

Current-platform check on 2026-09-27:

- The six Python files parse successfully under CPython 3.13.
- A temporary CPython 3.13 environment could load the workbooks with NumPy 2.5.3, Pandas 3.0.6 and openpyxl 3.1.5 after an I/O-path shim.
- `geatpy==2.7.0` was unavailable from the current PyPI index, which offered releases only through 2.4.0. The recovered native modules cannot load on macOS ARM64 or CPython 3.13.
- A minimal Geatpy `Problem` test double was therefore used only to instantiate `MyProblem` and call the unchanged decoder/cost functions. It did not simulate selection, crossover, mutation or Geatpy ranking.

`requirements-unpinned.txt` is an import inventory with the one confirmed framework version. It is not a historical lock file and must not be presented as the exact 2022 environment.
