# FHSS-Link firmware reference (host-testable, portable C99, no dynamic allocation)
HOST-TESTED ONLY. Not flashed, no radio used; hardware work starts 28 Oct (docs/BRINGUP_28OCT.md). Evidence and limits: docs/VALIDATION.md.

    make test    # unit tests + hop_engine vectors + cross-validation vs the Python references (needs python3 + numpy, run from firmware/ref)
    make san     # ASan/UBSan: tests, 2 fuzz seeds, full demo        make fuzz    # plain fuzz harness
    make logs    # regenerate logs/fw_*.log (dashboard: Source = Replay) and *.events.txt / *.summary.txt
    make nomalloc

| path | content |
|---|---|
| include/fh.h | whole API: SipHash-2-4, CRC, key derivation, keyed hop (Lemire), channel map, replay window, rolling counter, packets (CRC16 + 32-bit SipHash MAC), sync state machine, AFH scoring, ladder, serial protocol, safety guard |
| include/fh_link.h, src/fh_link.c | master/follower link logic built only on the HAL |
| hal/fh_radio.h | radio HAL; sim/mock_radio.c = deterministic mock medium + jammer |
| sim/demo.c | 3-node demo in one process (TX, RX, JAM behind the guard); options `--scenario clean\|static\|sweep\|random\|phases --slots N --seed S --kill-at SLOT --rx-boot-ms MS --out PREFIX`; `build/demo_host` uses `FH_SIM_UNSAFE_LIMITS`, `build/demo_safe` keeps the production guard caps |
| tests/ fuzz/ | unit tests, `xval.c/.py` cross-validation, mutation fuzz harness |
| logs/ | demo output: `$FH` serial logs, ladder/sync/guard event logs, summaries |
