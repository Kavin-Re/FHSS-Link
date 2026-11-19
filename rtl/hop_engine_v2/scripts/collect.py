"""Collect yosys results (results/synth/*) and simulated latencies into results/SUMMARY.txt. Pure text extraction; nothing typed in by hand."""
import re, os
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"); S = R + "/synth"
NAND2 = 3.7536
def rd(p): return open(p).read() if os.path.exists(p) else ""
sim = rd(R + "/sim_iverilog.log")
def lat(tag, dw):   # min/max/avg req->valid cycles from the testbench output of the default-config run
    m = re.search(r"TB\[%s\] cycles req->valid.*?min=(\d+) max=(\d+) avg=([\d.]+)" % tag, sim.split("DW=%d" % dw)[1] if ("DW=%d" % dw) in sim else sim)
    return m.group(1) if m else "?"
v1sim = rd(os.path.join(R, "..", "..", "..", "hopengine", "results", "sim_iverilog.log"))
m = re.search(r"TB\[m13\] cycles req->valid.*?min=(\d+) max=(\d+)", v1sim); v1lat = m.group(1) if m else "see v1 log"
def lat_of(dw):
    blk = [l for l in sim.splitlines() if l.startswith("TB[m13] DW=%d" % dw) or l.startswith("TB[m13] cycles")]
    i = [k for k, l in enumerate(blk) if l.startswith("TB[m13] DW=%d" % dw)]
    if not i: return "?"
    mm = re.search(r"min=(\d+) max=(\d+)", blk[i[0] + 1]); return mm.group(1)
rows = []
for tag, label, cyc in (("v1_keyed", "v1 keyed engine (4 adders/clk) [re-synthesised here]", v1lat),
                        ("lean64", "v2 lean, DW=64 (1 x 64-bit adder)", lat_of(64)),
                        ("lean32", "v2 lean, DW=32 (1 x 32-bit adder + carry flop)", lat_of(32)),
                        ("v1_lfsr13", "v1 LFSR16, M=13 (plain % 13 on 16 bit)", "1"),
                        ("lfsr_fold0", "v2 LFSR16 fold, FV=0 (8-bit % 13)", "1"),
                        ("lfsr_fold1", "v2 LFSR16 fold, FV=1 (no divider)", "1"),
                        ("wrap64", "v2 lean64 + beacon/AXI-lite wrapper", lat_of(64)),
                        ("wrap32", "v2 lean32 + beacon/AXI-lite wrapper", lat_of(32))):
    g = rd(f"{S}/{tag}_generic_stat.txt"); s = rd(f"{S}/{tag}_sky130_stat.txt"); t = rd(f"{S}/{tag}_timing_summary.txt"); l = rd(f"{S}/{tag}_generic_ltp.txt")
    gc = int(re.findall(r"Number of cells:\s+(\d+)", g)[-1]); sc = int(re.findall(r"Number of cells:\s+(\d+)", s)[0])
    area = float(re.findall(r"Chip area for module .*?: ([\d.]+)", s)[0]); ff = int(re.findall(r"dfxtp_1\s+(\d+)", s)[0])
    lv = int(re.findall(r"length=(\d+)", l)[0]); dn = dict(re.findall(r'WireLoad = "(\w+)".*?Delay =\s*([\d.]+) ps', t))
    rows.append((label, gc, lv, sc, ff, area, area / NAND2, float(dn["none"]), float(dn["Small"]), cyc))
byl = {r[0]: r for r in rows}
hdr = f"{'design':54s} {'generic':>7s} {'gate':>5s} | {'sky130':>6s} {'flops':>5s} {'area um2':>9s} {'GE':>6s} | {'delay ns':>8s} {'(SmallWL)':>9s} | {'clk req->valid':>14s}"
out = [hdr]
for r in rows: out.append(f"{r[0]:54s} {r[1]:7d} {r[2]:5d} | {r[3]:6d} {r[4]:5d} {r[5]:9.0f} {r[6]:6.0f} | {r[7]/1000:8.2f} {r[8]/1000:9.2f} | {r[9]:>14s}")
v1 = rows[0]
out += ["", "relative to v1 keyed (same script, same machine):"]
for r in rows[1:3]:
    out.append(f"  {r[0]:52s} area {100*(r[5]/v1[5]-1):+6.1f} %   flops {r[4]-v1[4]:+d}   latency {r[9]} vs {v1[9]} clk   area x latency = {r[5]*float(r[9])/(v1[5]*float(v1[9])):.2f} x v1")
l13 = rows[3]
for r in rows[4:6]: out.append(f"  {r[0]:52s} area {100*(r[5]/l13[5]-1):+6.1f} % vs v1 LFSR (mod 13)   delay {100*(r[7]/l13[7]-1):+.0f} % (no WL)")
out += ["", "generic cells = yosys synth + abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; gate depth = yosys ltp (flops cut)",
        "sky130 = yosys synth + dfflibmap + abc -liberty (-D 10000 ps) on sky130_fd_sc_hd__tt_025C_1v80 (dont_use copy); GE = area / 3.7536 um2",
        "delay = abc stime -p after map/buffer/upsize/dnsize; NO placement/routing, ideal clock, no setup/clk-to-q: optimistic combinational estimate, NOT sign-off timing",
        "latency = simulated clocks from the req sample to the valid pulse (iverilog testbench, retry-free hops)"]
open(R + "/SUMMARY.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
