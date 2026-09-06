# Rights and attribution

The historical project was team work by Zhuiguang for the 2022 Shanghai Open Data Innovative Application Competition. Jingfan Xin maintains this project repository and its English documentation. No claim of sole authorship of the full team platform or of third-party frameworks is made.

No repository-wide license has been added to the historical materials. A public repository is provided for inspection; contact the maintainer before reusing material whose permissions are unclear.

## Referenced software

- [Geatpy](https://github.com/geatpy-dev/geatpy): evolutionary optimization framework used by the historical route implementation. Its framework and examples are not redistributed here.
- [Ken Huang's multimodal transportation optimization](https://github.com/hzjken/multimodal-transportation-optimization): reference mathematical-programming project found in the source folder, not original project code.
- [MTRecS-DLT](https://github.com/Ayat-Abedalla/MTRecS-DLT): external transportation-recommendation research found among references; not part of the recovered routing implementation.
- Other KDD Cup and MATLAB reference archives are inventoried in [source recovery](docs/source-recovery.md) and are not vendored.

The original map exports identify Folium/Leaflet and external map/CDN services. Those HTML files and third-party tiles are not distributed here.

## Documents and data

The public repository contains small English transcriptions of project-specific parameters and aggregate simulation results, selected full-page renders from the semifinal and final team presentations, and two code screenshots embedded in the final presentation. The selected pages exclude team photographs, biographies and contact details. Original papers, certificates, source workbooks, complete competition submissions, complete competition data and mapping-provider datasets are not uploaded. Provenance hashes identify the reviewed evidence without exposing the maintainer's local filesystem paths.

The verification utilities, routing implementation, synthetic fixture, Geatpy integration and tests were developed with AI assistance. See [implementation provenance](docs/source-recovery.md). The integration calls Geatpy as a separately installed dependency; its source and compiled libraries are not vendored.
