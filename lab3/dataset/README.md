# Simulated jammer-classification dataset (FHSS-Link)

**All data here is SIMULATED.** Windows come from `sim/classify.py::sim_window` (a packet-level frequency-hopping link model); nothing was measured
on a radio. Use it to develop and compare classifiers, not to claim real-world accuracy.

Regenerate: `python3 lab3/make_dataset.py` (fixed seeds: generation 2026, split 12345). Baselines: `python3 lab3/dataset/baseline.py`.

## Files
| file | content |
|---|---|
| `windows.csv` | 6500 labelled windows (1300 per class), column `split` = `train` (5200) or `test` (1300), stratified 80/20 |
| `baseline.py` | numpy-only baselines (majority, nearest centroid, softmax regression); needs only `windows.csv` |
| `raw/*.log` | 4 raw logs of 1500 slots each (jammer none/static/sweep/random vs a blind-hopping defender, M=13) in the board serial format `$FH,<slot>,<ch>,<ok>,<retries>,<rssi>*<CRC8>` (see `docs/SERIAL_FORMAT.md`), produced by `sim/emu_device.py`. No raw log for `reactive` (the emulator has no such jammer). |

## Columns of `windows.csv`
Metadata: `id`, `split`, `label` (none / static / sweep / random / reactive), `M` (hop channels: 8, 13, 16, 24, 32), `W` (window length in slots: 100, 150, 200),
`duty` (jammer duty 1.0 / 0.75 / 0.5 / 0.25; irrelevant for `none`), `p_jam` (loss probability on a jammed hop, U(0.5, 0.99)), `p_clean` (background loss, U(0.005, 0.04)),
`seed` (seed passed to `sim_window`; with the same `classify.py` the window can be regenerated).

Features (what the link can observe over one window; computed over the *lost* packets `lc` unless noted):
| column | definition |
|---|---|
| `rate` | fraction of slots whose packet was lost |
| `top2_loss_share` | share of losses that fall on the two most-hit channels |
| `step_plus1` | fraction of consecutive lost packets whose channel differs by +1 (mod M) |
| `loss_entropy` | Shannon entropy of the loss-channel histogram, divided by log2(M) |
| `rssi_excess` | (mean RSSI of lost packets - mean RSSI of delivered packets) / 10 dB |
| `repeat_rate` | fraction of consecutive lost packets on the same channel |
| `phase_peak` | share of losses that have the most common value of (channel - slot index) mod M (sweep signature) |

If a window has fewer than 3 lost packets, all features except `rate` are 0 (about 14 % of windows, mostly `none`, but also quiet `static`/`sweep`/`random` windows).
These are inherently ambiguous and are deliberately kept.

## Labels
`none` no jammer; `static` 1-3 fixed jammed channels; `sweep` 1-3 channels advancing by one per slot; `random` 1-3 random channels per slot;
`reactive` a jammer that has already broken our LFSR hop schedule and predicts our channel (`sim/attack.py`).

## Known limits
Simulated physics only; one defender policy (blind hopping); jammer models are the simple ones in `sim/adaptive.py` and `sim/attack.py`;
the same hop schedule family (16-bit LFSR) for the `reactive` class. Accuracy on these windows says nothing about real RF conditions.

## License
MIT License. Copyright (c) 2026 the FHSS-Link project authors. Permission is hereby granted, free of charge, to any person obtaining a copy of this dataset
and associated files, to deal in them without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies, subject to the inclusion of this notice. THE DATA AND SCRIPTS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
