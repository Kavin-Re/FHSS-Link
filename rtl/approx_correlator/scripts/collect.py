"""Collect yosys results (results/synth/*) and BER csv into results/SUMMARY.txt. Pure text extraction; nothing typed in by hand."""
import re, os, csv
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"); S = R + "/synth"; NAND2 = 3.7536
def rd(p): return open(p).read() if os.path.exists(p) else ""
def get(tag):
    g = rd(f"{S}/{tag}_generic_stat.txt"); s = rd(f"{S}/{tag}_sky130_stat.txt"); t = rd(f"{S}/{tag}_timing_summary.txt"); l = rd(f"{S}/{tag}_generic_ltp.txt")
    ff = re.findall(r"dfxtp_1\s+(\d+)", s)
    return dict(gc=int(re.findall(r"Number of cells:\s+(\d+)", g)[-1]), sc=int(re.findall(r"Number of cells:\s+(\d+)", s)[0]),
                area=float(re.findall(r"Chip area for module .*?: ([\d.]+)", s)[0]), ff=int(ff[0]) if ff else 0, lv=int(re.findall(r"length=(\d+)", l)[0]),
                dn=float(dict(re.findall(r'WireLoad = "(\w+)".*?Delay =\s*([\d.]+) ps', t))["none"]))
out = ["A) static combinational correlator core (corr_core, DYN=0: unmodified ApproxKit adder cells, COMP=0), sky130 tt_025C_1v80 via yosys 0.33, no P&R",
       f"{'N':>3s} {'adders':>14s} {'sky130 cells':>12s} {'area um2':>9s} {'GE':>6s} {'vs exact':>9s} {'gate depth':>10s} {'delay ns (no WL)':>16s}"]
for N in (16, 32, 64):
    ex = get(f"core_N{N}_exact")
    for nm in ("exact", "LOA1", "LOA2", "LOA3", "TRUNC2", "ETA3"):
        d = get(f"core_N{N}_{nm}")
        out.append(f"{N:3d} {nm:>14s} {d['sc']:12d} {d['area']:9.0f} {d['area']/NAND2:6.0f} {100*(d['area']/ex['area']-1):+8.1f}% {d['lv']:10d} {d['dn']/1000:16.2f}")
out += ["", "B) full ladder-driven block approx_correlator (dual_adder cells switchable at run time + corr_mode_ctrl + output registers), COMP = calibrated constant for LOA3",
        f"{'N':>3s} {'variant':>22s} {'sky130 cells':>12s} {'flops':>5s} {'area um2':>9s} {'GE':>6s} {'vs exact core':>14s} {'vs ATYPE=0 blk':>14s} {'delay ns (no WL)':>16s}"]
for N in (16, 32, 64):
    ex = get(f"core_N{N}_exact"); ec = get(f"dyn_N{N}_exact_ctrl")
    for nm, lab in (("exact_ctrl", "ATYPE=0 (exact only)"), ("LOA3", "LOA3 switchable")):
        d = get(f"dyn_N{N}_{nm}")
        out.append(f"{N:3d} {lab:>22s} {d['sc']:12d} {d['ff']:5d} {d['area']:9.0f} {d['area']/NAND2:6.0f} {100*(d['area']/ex['area']-1):+13.1f}% {100*(d['area']/ec['area']-1):+13.1f}% {d['dn']/1000:16.2f}")
out += ["", "note: the area saving of approximate adders is only realised when the approximate mode is the only mode (table A); the switchable block (table B) carries both the exact and the approximate low part.",
        "      power was NOT estimated; the saving shown is cell area only.  'vs exact core' in B is relative to the static exact core of table A (same N).",
        "      delay = abc stime after map/buffer/upsize/dnsize, no placement/routing, NOT sign-off timing."]
rows = list(csv.DictReader(open(R + "/ber_vs_snr.csv"))); idx = {(int(r["N"]), r["config"], int(r["ebn0_db"])): r for r in rows}
nb = rows[0]["bits"]
out += ["", f"C) BER vs Eb/N0 (Python bit-exact model, {nb} bits/point, 6-bit ADC step 0.5, AWGN, random code per bit; '*' = fewer than 30 errors)",
        f"{'N':>3s} {'config':>12s} " + "".join(f"{s:>9d}dB" for s in (2, 4, 6, 8))]
for N in (16, 32, 64):
    for cn in ("exact", "LOA1", "LOA1+comp", "LOA2+comp", "LOA3+comp", "TRUNC1+comp", "ETA1+comp"):
        line = f"{N:3d} {cn:>12s} "
        for s in (2, 4, 6, 8):
            r = idx[(N, cn, s)]; line += f"{float(r['ber']):>10.2e}{'*' if int(r['errors']) < 30 else ' '}"
        out.append(line)
out.append("(full table: ber_vs_snr.txt / .csv / .png)")
open(R + "/SUMMARY.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
