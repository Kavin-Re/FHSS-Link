"""Emulated board: runs the simulator and prints the same lines the real firmware will print.
usage: python3 emu_device.py --defender keyed --jammer sweep --slots 3000 --out ../logs/demo.log"""
import argparse, os
import numpy as np
from serial_proto import encode
from adaptive import make_policy, Jammer

def emulate(defender="blind", jammer="static", M=13, slots=3000, seed=1, p_jam=0.95, p_clean=0.01):
    rng = np.random.default_rng(seed)
    pol = make_policy(defender, M, np.random.default_rng(seed + 1)); jam = Jammer(jammer, M, np.random.default_rng(seed + 2)) if jammer != "none" else None
    for t in range(slots):
        J = jam.jammed() if jam else set()
        c = pol.pick(); jammed = c in J
        ok = rng.random() > (p_jam if jammed else p_clean)
        pol.update(c, float(ok))
        if jam: jam.observe(c)
        rssi = int(round(-62 + rng.normal(0, 2) + (14 if jammed else 0)))   # energy rises on a jammed channel
        yield encode(t, c, ok, 0 if ok else 1, rssi), dict(slot=t, ch=c, ok=ok, jammed=jammed, rssi=rssi)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--defender", default="blind"); ap.add_argument("--jammer", default="static")
    ap.add_argument("--slots", type=int, default=3000); ap.add_argument("--out", default="-"); a = ap.parse_args()
    f = open(a.out, "w") if a.out != "-" else None
    for line, _ in emulate(a.defender, a.jammer, slots=a.slots):
        (f.write(line) if f else print(line, end=""))
