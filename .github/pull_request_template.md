## Summary

What does this change and why?

## Checklist

- [ ] `./run_tests.sh` passes
- [ ] C reference: `make -C firmware/ref test` (and `san` for memory-safety changes) passes
- [ ] RTL changes: `rtl/hop_engine/scripts/run_all.sh` re-run, or state "not run" with tool versions
- [ ] No simulation result is described as a hardware measurement
- [ ] Documentation updated where behaviour changed
- [ ] No secrets, keys or personal data committed

## Test notes

How was this verified? Paste commands and results, or write "not run".
