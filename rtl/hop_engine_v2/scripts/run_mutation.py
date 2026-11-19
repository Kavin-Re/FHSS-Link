#!/usr/bin/env python3
"""Mutation check of the v2 testbenches: apply one hand-made bug at a time to a copy of the RTL, run the (reduced-length) self-checking
benches, and report whether the bug is caught (bench prints FAIL or does not PASS).  Every row must be CAUGHT for the check to pass."""
import os, subprocess, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VD = f'"{ROOT}/vectors/"'; OD = '"%s/build/"' % ROOT
ENG = open(f"{ROOT}/rtl/hop_keyed_lean.v").read(); WRP = open(f"{ROOT}/rtl/hop_sync_axil.v").read(); LF = open(f"{ROOT}/rtl/hop_lfsr_fold.v").read()
ENG_MUT = [
 ("rotl13 -> rotl12", "{v1[50:0], v1[63:51]}", "{v1[51:0], v1[63:52]}"),
 ("rotl16(v3) wrong", "{v3[47:0], v3[63:48]}", "{v3[46:0], v3[63:47]}"),
 ("rotl21(v3) wrong", "{v3[42:0], v3[63:43]}", "{v3[41:0], v3[63:42]}"),
 ("rotl17(v1) wrong", "{v1[46:0], v1[63:47]}", "{v1[45:0], v1[63:46]}"),
 ("rotl32 of op0 dropped", "2'd0: begin v0 <= rot32s;", "2'd0: begin v0 <= s;"),
 ("operand mux op2 uses v1", "(op[0] ^ op[1]) ? v3 : v1", "(op[0]) ? v3 : v1"),
 ("final-block constant wrong", "BLK = 64'h0800000000000000", "BLK = 64'h0900000000000000"),
 ("0xff xor wrong", "64'hff : 64'd0", "64'h7f : 64'd0"),
 ("msg xor at wrong round", "(rnd == 3'd1) ? msg", "(rnd == 3'd2) ? msg"),
 ("threshold wrong (needs RW=8 configs)", "THR = TWO_RW % M", "THR = (TWO_RW % M) + 1"),
 ("retry increment wrong", "retry <= retry + 8'd1", "retry <= retry + 8'd2"),
 ("slot increment wrong", "slot_r <= slot_r + 56'd1", "slot_r <= slot_r + 56'd2"),
 ("chunk shift wrong", "v0 <= v0 >> RW", "v0 <= v0 >> (RW-1)"),
 ("DW=32 carry dropped", "{32'd0, (half & cy)}", "33'd0"),
 ("DW=32 carry not stored", "cy <= s32[32]", "cy <= 1'b0"),
]
WRP_MUT = [
 ("beacon compare inverted", "bcn_slot_q == slot_cur", "bcn_slot_q != slot_cur"),
 ("since-beacon not restarted", "bcn_slot_q <= beacon_slot; since_bcn <= 16'd0;", "bcn_slot_q <= beacon_slot;"),
 ("overrun never set", "if (busy || tick_pend) st_overrun <= 1'b1;", ""),
 ("busy key write not blocked", "wire key_blocked = w_key && busy;", "wire key_blocked = 1'b0;"),
 ("SLOT_HI width", "slot_stage[55:32] <= s_wdata[23:0]", "slot_stage[55:32] <= {1'b0, s_wdata[22:0]}"),
 ("hop counter not counting", "hopcnt <= hopcnt + 32'd1; chan_last <= ec;", "chan_last <= ec;"),
 ("holdover compare off by one", "(since_bcn >= holdover)", "(since_bcn > holdover)"),
 ("beacon accepted while BCN_EN=0", "if (beacon_valid && bcn_en)", "if (beacon_valid)"),
 ("drift not sticky", "st_drift <= 1'b1; end", "end"),
 ("key readable", "default:  rd_mux = 32'd0;", "A_KEY0: rd_mux = 32'h1; default:  rd_mux = 32'd0;"),
]
LF_MUT = [
 ("fold constant +2 -> +1", "8'd2;\n    reg", "8'd1;\n    reg"),
 ("fold sign (b not inverted)", "{2'd0, ~sn[11:6]}", "{2'd0, sn[11:6]}"),
 ("second fold threshold 26->27", "7'd26", "7'd27"),
]
def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140); return r.stdout + r.stderr
def run_eng(src, tmp):
    out = []
    p = f"{tmp}/e.v"; open(p, "w").write(src)
    for tag, M, RW, NCH, DW, ns in (("m13_rw8", 13, 8, 1, 64, 1500), ("m13_rw8n4", 13, 8, 4, 32, 1000), ("m13", 13, 32, 2, 32, 150)):
        sh(f"iverilog -g2005 -o {tmp}/s -DTAG='\"{tag}\"' -DM={M} -DRW={RW} -DNCH={NCH} -DDW={DW} -DNKEY=1 -DNSLOT={ns} -DNDIG=100 -DVDIR='{VD}' -DODIR='\"{tmp}/\"' {ROOT}/tb/tb_hop_keyed_lean.v {p}")
        out.append("PASS" in sh(f"vvp -n {tmp}/s | grep RESULT"))
    return all(out)
def run_wrp(src, tmp):
    p = f"{tmp}/w.v"; open(p, "w").write(src); ok = True
    for dw in (64, 32):
        sh(f"iverilog -g2005 -o {tmp}/sw -DDW={dw} -DNOPS=1976 -DVDIR='{VD}' {ROOT}/tb/tb_hop_sync_axil.v {p} {ROOT}/rtl/hop_keyed_lean.v")
        ok &= "PASS" in sh(f"vvp -n {tmp}/sw | grep RESULT")
        if not ok: break
    return ok
def run_lf(src, tmp):
    p = f"{tmp}/l.v"; open(p, "w").write(src)
    sh(f"iverilog -g2005 -o {tmp}/sl -DFV=1 -DVDIR='{VD}' {ROOT}/tb/tb_hop_lfsr_fold.v {p}")
    return "PASS" in sh(f"vvp -n {tmp}/sl | grep RESULT")
if __name__ == "__main__":
    os.makedirs(f"{ROOT}/build", exist_ok=True); tmp = tempfile.mkdtemp(); rows = []; bad = 0
    base = run_eng(ENG, tmp) and run_wrp(WRP, tmp) and run_lf(LF, tmp)
    print("unmutated baseline passes:", base); bad += (not base)
    for grp, src, muts, fn in (("engine", ENG, ENG_MUT, run_eng), ("wrapper", WRP, WRP_MUT, run_wrp), ("lfsr_fold", LF, LF_MUT, run_lf)):
        for name, a, b in muts:
            if a not in src: print(f"[{grp}] {name}: PATTERN NOT FOUND"); bad += 1; continue
            passed = fn(src.replace(a, b, 1), tmp); bad += passed
            print(f"[{grp}] {name}: {'NOT CAUGHT' if passed else 'caught'}")
    print("mutations not caught or errors:", bad); sys.exit(1 if bad else 0)
