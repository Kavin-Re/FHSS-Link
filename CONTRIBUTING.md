# Contributing to FHSS-Link

Thanks for your interest. FHSS-Link holds simulators, a C firmware reference and RTL for frequency-hopping link resilience (student project; simulation only).

## Getting started

```
pip install -e .                      # numpy; add matplotlib for plots
python -m fhss_lab bench
```

## Testing

```
./run_tests.sh                        # Python simulators, labs, hop-engine model; 2-3 minutes
make -C firmware/ref test             # C reference, host gcc
make -C firmware/ref san              # same under ASan/UBSan, plus fuzz
rtl/hop_engine/scripts/run_all.sh     # lint, iverilog/Verilator sims, Yosys, formal (not run in CI)
```

`run_tests.sh` is what CI runs (plus `python -m fhss_lab bench`); the RTL flow needs iverilog, Verilator, Yosys, SymbiYosys and z3. State tool versions with any RTL change.

## Pull requests

- Open an issue first for larger changes.
- Keep PRs focused and fill in the pull request template.
- Follow `.editorconfig` and match the style of surrounding code.
- Say which simulator and tool versions you used for RTL changes.

## Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
