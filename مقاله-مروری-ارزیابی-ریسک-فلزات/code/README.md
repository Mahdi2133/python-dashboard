# Code (File S3)

Python 3.11+ with numpy, scipy, matplotlib, openpyxl. Run from this folder.

| Step | Command | Output |
|---|---|---|
| Parse canned-fish table (S10) | `python parse_s10.py <pdftotext -raw output of Kosker 2023>` | `s10_parsed.json` |
| Meta-analysis (REML + HKSJ, leave-one-out) | `python run_ma.py` | `ma_results.json`, `ma_table.csv` |
| Forest plots | `python forest.py` | `fig_forest.png/pdf/svg` |
| Integrated equation, worked example + Monte Carlo | `python worked_example.py` | `worked_example.json` |
| Other figures | `python figs.py` | PRISMA, evidence map, framework, worked example |
| Excel calculator | `python build_calculator.py Integrated_HRA_Calculator.xlsx` | calculator with live formulas |

- `ma_engine.py` validates itself against metafor (`python ma_engine.py`, BCG data).
- `integrated_hra.py` holds the equations (Eq. 1-10) and the toxicity values; use `monte_carlo()` with your own
  distributions and an inter-media correlation `rho` for the applied study.
