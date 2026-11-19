"""Python reference + stimulus generator for rtl/hop_sync_axil.v (register-level, cycle-independent: every op is applied to the model in
program order; the testbench spaces the ops so the RTL has finished the previous one).  Writes vectors/wrap_{ops,arg,exp}.mem.
Hop values come from hop_model.hop (bit-exact SipHash-2-4 model, shared with the engine tests)."""
import os, sys, random
sys.path.insert(0, os.path.dirname(__file__))
from hop_model import hop
V = os.path.join(os.path.dirname(__file__), "..", "vectors"); os.makedirs(V, exist_ok=True)
A = dict(CTRL=0x00, STATUS=0x04, KEY0=0x08, KEY1=0x0C, KEY2=0x10, KEY3=0x14, SLO=0x18, SHI=0x1C, BCN=0x20, HOLD=0x24, HOPC=0x28, ID=0x2C)
M, RW, NCH = 13, 32, 2
OP_WR, OP_RD, OP_TICK, OP_BCN, OP_IDLE, OP_TICKBCN, OP_TICK2, OP_TICKKEYW, OP_SOFT = 1, 2, 3, 4, 5, 6, 7, 8, 9
SL = (1 << 56) - 1

class Model:
    def __init__(s):
        s.key = [0, 0, 0, 0]; s.loaded = False; s.slot = 0; s.stage = 0; s.en = 0; s.bcn_en = 0; s.hold = 0; s.since = 0
        s.lock = 0; s.drift = 0; s.hopcnt = 0; s.chan_last = 0; s.overrun = s.drift_st = s.nokey = s.keyerr = 0
    def key128(s): return sum(w << (32 * i) for i, w in enumerate(s.key))
    def lost(s): return int(s.hold != 0 and s.since >= s.hold)
    def status(s):
        return (s.chan_last << 16) | (s.keyerr << 9) | (s.nokey << 8) | (s.drift_st << 7) | (s.overrun << 6) | (s.lost() << 5) | (int(s.loaded) << 1)
    def tick(s, second_while_busy=False):
        if not s.en: return None
        s.since = min(s.since + 1, 0xFFFF)
        if not s.loaded: s.nokey = 1; return None
        if second_while_busy: s.overrun = 1
        c = hop(s.key128(), s.slot, M, RW, NCH)[0]
        s.slot = (s.slot + 1) & SL; s.hopcnt += 1; s.chan_last = c
        return c
    def beacon(s, b):
        if not s.bcn_en: return
        if b == s.slot: s.lock = min(s.lock + 1, 0xFFFF)
        else: s.drift = min(s.drift + 1, 0xFFFF); s.drift_st = 1
        s.slot = b; s.since = 0
    def reg_write(s, a, d):
        if a == A["CTRL"]:
            s.en = d & 1; s.bcn_en = (d >> 4) & 1
            if d & 4: s.overrun = s.drift_st = s.nokey = s.keyerr = 0
            if d & 8: s.lock = s.drift = s.hopcnt = 0
            if d & 2: return s.tick()               # soft tick (uses the EN value written in the same transaction)
        elif a in (A["KEY0"], A["KEY1"], A["KEY2"], A["KEY3"]):
            i = (a - A["KEY0"]) // 4; s.key[i] = d
            if i == 3: s.loaded = True
        elif a == A["SLO"]: s.stage = (s.stage & ~0xFFFFFFFF) | d
        elif a == A["SHI"]: s.stage = (s.stage & 0xFFFFFFFF) | ((d & 0xFFFFFF) << 32); s.slot = s.stage
        elif a == A["HOLD"]: s.hold = d & 0xFFFF
        return None
    def reg_read(s, a):   # (mask, value)
        if a == A["CTRL"]: return 0xFFFFFFFF, (s.bcn_en << 4) | s.en
        if a == A["STATUS"]: return 0xFFFFFFFF, s.status()
        if a == A["SLO"]: return 0xFFFFFFFF, s.slot & 0xFFFFFFFF
        if a == A["SHI"]: return 0xFFFFFFFF, s.slot >> 32
        if a == A["BCN"]: return 0xFFFFFFFF, (s.drift << 16) | s.lock
        if a == A["HOLD"]: return 0xFFFFFFFF, s.hold
        if a == A["HOPC"]: return 0xFFFFFFFF, s.hopcnt & 0xFFFFFFFF
        if a == A["ID"]: return 0xFFFFFFFF, 0x48530001
        return 0xFFFFFFFF, 0

def generate(seed=20261007, nrounds=140):
    rnd = random.Random(seed); m = Model(); ops = []
    def emit(op, arg=0, exp=0): ops.append((op, arg, exp))
    def wr(a, d, resp=0): m.reg_write(a, d) if resp == 0 else None; emit(OP_WR, (a << 32) | d, resp)
    def rd(a, resp=0):
        mask, val = m.reg_read(a); emit(OP_RD, a | (resp << 32), (mask << 32) | val)
    def load_key(k):
        for i in range(4): wr(A["KEY0"] + 4 * i, (k >> (32 * i)) & 0xFFFFFFFF)
    def set_slot(sv):
        wr(A["SLO"], sv & 0xFFFFFFFF); wr(A["SHI"], sv >> 32)
    # --- directed prologue ---
    rd(A["ID"]); rd(A["STATUS"]); rd(A["KEY0"])                       # reset values; KEY reads 0
    emit(OP_TICK, 0, 0)                                               # EN=0: tick ignored, no hop
    wr(A["CTRL"], 1); rd(A["CTRL"])
    m.tick(); emit(OP_TICK, 0, 0)                                     # EN, no key: nokey sticky, no hop
    rd(A["STATUS"])
    wr(0x30, 0x1234, resp=2); rd(0x30, resp=2); rd(0x34, resp=2)        # unmapped address -> SLVERR (writes have no effect)
    key = int.from_bytes(bytes(range(16)), "little"); load_key(key); set_slot(0x00ABCDEF12345600)
    wr(A["CTRL"], 0x0D)                                               # EN | CLR_STICKY | CLR_CNT
    rd(A["STATUS"]); rd(A["SLO"]); rd(A["SHI"])
    for _ in range(5):
        c = m.tick(); emit(OP_TICK, 0, (1 << 8) | c)
    rd(A["STATUS"]); rd(A["HOPC"]); rd(A["SLO"])
    # --- random body ---
    keys = [key] + [rnd.getrandbits(128) for _ in range(3)]
    for r in range(nrounds):
        sel = rnd.random()
        if sel < 0.10:                                                # rekey + reslot, via registers
            key = rnd.choice(keys) if rnd.random() < 0.5 else rnd.getrandbits(128); load_key(key)
            set_slot(rnd.choice([rnd.getrandbits(56), SL - rnd.randrange(3), rnd.randrange(1 << 20)]))
        elif sel < 0.16:
            wr(A["HOLD"], rnd.choice([0, 3, 5, 8, 20])); rd(A["HOLD"])
        elif sel < 0.20:
            wr(A["CTRL"], rnd.choice([0x01, 0x11, 0x15, 0x19, 0x1D, 0x10, 0x00, 0x11]))
            if not m.en: emit(OP_TICK, 0, 0)
            if not m.en: wr(A["CTRL"], 0x11)
        for _ in range(rnd.randrange(2, 12)):
            t = rnd.random()
            if t < 0.55:
                c = m.tick()
                emit(OP_TICK, 0, ((1 << 8) | c) if c is not None else 0)
            elif t < 0.70:
                c = m.tick(); emit(OP_TICK, 0, ((1 << 8) | c) if c is not None else 0)
                nb = m.slot if rnd.random() < 0.6 else (m.slot + rnd.choice([1, 2, 7, 1000])) & SL    # in-sync beacon or drifted one
                m.beacon(nb); emit(OP_BCN, nb, 0)
            elif t < 0.80:                                            # beacon arrives while the tick's hop is in flight
                c = m.tick(); nb = m.slot if rnd.random() < 0.5 else (m.slot + rnd.choice([1, 3, 50])) & SL
                m.beacon(nb); emit(OP_TICKBCN, nb | (rnd.randrange(3, 9) << 120), ((1 << 8) | c) if c is not None else 0)
            elif t < 0.86:                                            # second tick arrives while busy -> OVERRUN, both hops delivered
                c1 = m.tick(); c2 = m.tick(second_while_busy=True)
                emit(OP_TICK2, 0, (0x100 | (c2 << 4) | c1) if c1 is not None else 0)
            elif t < 0.90 and m.en and m.loaded:                      # key word written while busy -> SLVERR, no effect, KEYERR sticky
                c = m.tick(); m.keyerr = 1
                emit(OP_TICKKEYW, rnd.getrandbits(32), (1 << 8) | c)
            elif t < 0.95:
                emit(OP_IDLE, rnd.randrange(1, 40), 0)
            else:
                rd(rnd.choice([A["STATUS"], A["BCN"], A["HOPC"], A["SLO"], A["SHI"], A["CTRL"]]))
        rd(A["STATUS"]); rd(A["BCN"]); rd(A["SLO"]); rd(A["SHI"]); rd(A["HOPC"])
        if rnd.random() < 0.4: wr(A["CTRL"], 0x15 if m.en else 0x14)  # clear sticky
    # soft ticks (CTRL.SOFT_TICK) : EN | SOFT_TICK | BCN_EN
    for _ in range(4):
        d = 0x13; c = m.reg_write(A["CTRL"], d)
        emit(OP_SOFT, d, ((1 << 8) | c) if c is not None else 0)
        rd(A["HOPC"]); rd(A["STATUS"])
    return ops, m

if __name__ == "__main__":
    ops, m = generate()
    open(f"{V}/wrap_ops.mem", "w").write("\n".join("%02x" % o[0] for o in ops) + "\n")
    open(f"{V}/wrap_arg.mem", "w").write("\n".join("%032x" % o[1] for o in ops) + "\n")
    open(f"{V}/wrap_exp.mem", "w").write("\n".join("%016x" % o[2] for o in ops) + "\n")
    from collections import Counter
    print("wrap ops:", len(ops), dict(Counter(o[0] for o in ops)), "final model: hops=%d lock=%d drift=%d" % (m.hopcnt, m.lock, m.drift))
