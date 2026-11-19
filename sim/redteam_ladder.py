"""Two red-team experiments against our own ladder (simulation, own-link model only).
A) Timing leak: critical messages are periodic (every 10 slots). An attacker that learns the period jams ALL channels in w slots per period
   (airtime w/10). Compare: periodic message schedule vs randomised start offset. Critical delivery for 1, 3, 5, 10 attempts.
B) Mode-forcing attack: short wideband bursts (30 slots every 400 = 7.5% airtime) push the ladder into CODED/SURVIVAL; measure bulk goodput lost
   per slot the attacker spends, vs plain ADAPT (no ladder)."""
import numpy as np
import ladder

def timing_leak(tries, w, randomised, seed=1, T=20000, p_jam=0.95, p_clean=0.01):
    rng = np.random.default_rng(seed); ok = n = 0
    for k in range(T // 10):
        base = k * 10; off = int(rng.integers(0, 10)) if randomised else 0
        n += 1
        for a in range(tries):
            t = base + off + a
            jammed = (t % 10) < w            # attacker jams slots 0..w-1 of every period, all channels
            if rng.random() > (p_jam if jammed else p_clean): ok += 1; break
    return ok / n

def mode_forcing(policy, seed=1):
    ladder.PHASES = [(0, 10000, "attack")]
    def js(t, rng, M=13): return set(range(8)) if (t % 400) < 30 else set()
    ladder.jam_set = js; ladder.phase_name = lambda t: "attack"
    out = ladder.run(policy, seed=seed)["attack"]; return out

if __name__ == "__main__":
    print("A) critical delivery under timed bursts (attacker airtime = w/10 of all slots)")
    for w in (1, 3):
        for tries in (1, 3, 5, 10):
            print(f"  w={w} attempts={tries:2d}: periodic {timing_leak(tries, w, False):.2f}   randomised {timing_leak(tries, w, True):.2f}")
    print("B) 10,000 slots, bursts of 30 slots (8 of 13 channels) every 400 slots: attacker airtime 7.5%")
    for pol in ("NORMAL", "ADAPT", "LADDER"):
        r = np.mean([mode_forcing(pol, s)["bulk"] for s in (1, 2, 3)]); c = np.mean([mode_forcing(pol, s)["critical"] for s in (1, 2, 3)])
        print(f"  {pol:7s} bulk goodput {r:.3f}  critical {c:.3f}")
