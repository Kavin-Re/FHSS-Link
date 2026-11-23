# Origin of this folder

| | |
|---|---|
| Source repository | https://github.com/Kavin-Re/HopBench (archived on 2026-11-23) |
| Source commit | `4859f08e5613a672a952962e2e804b201974dc57` ("Repository overhaul: docs, tests, CI, fixes", 2026-11-19) |
| Copied on | 2026-11-23, with `git archive` of that commit |
| Left out | `.github/` (its CI job now runs from FHSS-Link's `.github/workflows/tests.yml`) |
| Changed after copying | `README.md` (this origin note, clone path, roadmap, licence), `CITATION.cff` (repository address, licence), `CODE_OF_CONDUCT.md` (issue address), this file |

The full history of the files before the copy stays in the archived HopBench repository.

Check made when copying: `python3 -m pytest -q` passed (93 tests), and a fresh reference run
(`python3 -m hopbench run --out <dir> --jobs 4`) reproduced `results/leaderboard.csv` exactly; in
`results/results.md` only the wall time differed.
