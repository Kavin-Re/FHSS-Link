"""Collect the yosys results (results/synth/*) into results/SUMMARY.txt. Pure text extraction, no numbers are typed in by hand."""
import re, os
R = os.path.join(os.path.dirname(__file__), "..", "results"); S = R + "/synth"
NAND2 = 3.7536     # sky130_fd_sc_hd__nand2_1 area in um^2 (from the liberty file used)
def rd(p): return open(p).read() if os.path.exists(p) else ""
rows = []
for tag, label in (("lfsr_m16", "LFSR16, M=16 (mod = wiring; LFSR core only)"), ("lfsr_m13", "LFSR16, M=13 (reference engine)"),
                   ("keyed_m13", "Keyed SipHash-2-4 + Lemire, M=13 (default adders)"), ("keyed_m13_ripple", "Keyed, M=13, RIPPLE=1 adders")):
    g = rd(f"{S}/{tag}_generic_stat.txt"); s = rd(f"{S}/{tag}_sky130_stat.txt"); t = rd(f"{S}/{tag}_timing_summary.txt"); l = rd(f"{S}/{tag}_generic_ltp.txt")
    gc = int(re.findall(r"Number of cells:\s+(\d+)", g)[-1])
    sc = int(re.findall(r"Number of cells:\s+(\d+)", s)[0]); area = float(re.findall(r"Chip area for module .*?: ([\d.]+)", s)[0])
    ff = int(re.findall(r"dfxtp_1\s+(\d+)", s)[0])
    lv = int(re.findall(r"length=(\d+)", l)[0])
    d = re.findall(r'WireLoad = "(\w+)".*?Delay =\s*([\d.]+) ps', t)
    dn = dict(d)
    rows.append((label, gc, lv, sc, ff, area, area / NAND2, float(dn.get("none", 0)), float(dn.get("Small", 0))))
hdr = f"{'engine':52s} {'generic':>8s} {'gate':>5s} | {'sky130':>7s} {'flops':>6s} {'area um2':>10s} {'NAND2-eq':>9s} | {'abc delay ns':>13s} {'(Small WL)':>10s}"
out = [hdr, f"{'':52s} {'cells':>8s} {'depth':>5s} | {'cells':>7s} {'':>6s} {'':>10s} {'(GE)':>9s} | {'no WL':>13s}"]
for r in rows: out.append(f"{r[0]:52s} {r[1]:8d} {r[2]:5d} | {r[3]:7d} {r[4]:6d} {r[5]:10.0f} {r[6]:9.0f} | {r[7]/1000:13.2f} {r[8]/1000:10.2f}")
out.append("")
out.append("generic cells = yosys 'synth' + abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX, gate depth = yosys ltp (longest topological path in cells, flops cut)")
out.append("sky130 cells/area = yosys synth + dfflibmap + abc -liberty (-D 10000 ps target) on sky130_fd_sc_hd__tt_025C_1v80; GE = area / 3.7536 um2 (nand2_1)")
out.append("abc delay = abc 'stime -p' after map+buffer+upsize+dnsize; NO placement/routing, ideal clock, no setup/clk-to-q: an optimistic combinational estimate, NOT sign-off timing")
open(R + "/SUMMARY.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
