"""R3 (RED_TEAM idea 6) Selective jamming of the control plane. Model of our own link: data hops uniformly over 13 channels; a beacon every B=20 slots
on one of R rendezvous channels re-anchors the slot counter. The receiver loses sync if no beacon arrives for D slots; when out of sync it
can only listen on a random one of the R rendezvous channels per beacon period (it cannot compute the keyed beacon channel without sync).
Jammer budget = one channel at a time. 'data' mode: sits on data channel 0 forever (duty 100% of slots on one channel). 'control' mode: transmits only in
beacon slots (duty 1/B), on a random one of the R rendezvous channels (it knows the set, not the keyed pick). Metric = availability (delivered data slots / slots)."""
import numpy as np
from _common import *

def run(R, D, mode, T=60000, B=20, seed=0, M=M_DEF):
    rng = np.random.default_rng(seed); synced = True; since = 0; deliv = 0; jam_slots = 0
    for t in range(T):
        beacon = (t % B == 0)
        if beacon:
            jam_ch = int(rng.integers(R)) if mode == "control" else -1       # jammer's pick among the R rendezvous channels
            if mode == "control": jam_slots += 1
            bc = int(rng.integers(R))                                            # keyed beacon channel
            lis = bc if synced else int(rng.integers(R))                         # receiver knows it only while synced
            hit = (jam_ch == bc) and rng.random() < P_JAM
            if lis == bc and not hit and rng.random() > P_CLEAN:
                synced = True; since = 0
        if synced:
            since += 1
            if since > D: synced = False
        if mode == "data": jam_slots += 1
        if synced:
            ch = int(rng.integers(M)); lost = (mode == "data" and ch == 0 and rng.random() < P_JAM) or rng.random() < P_CLEAN
            deliv += (not lost)
    return dict(avail=deliv / T, duty=jam_slots / T)

def avg(R, D, mode, seeds=range(4), **kw):
    r = [run(R, D, mode, seed=s, **kw) for s in seeds]; return {k: float(np.mean([x[k] for x in r])) for k in r[0]}

CONFIGS = {"R=1, D=60 (naive)": (1, 60), "R=3, D=60": (3, 60), "R=5, D=100": (5, 100), "R=5, D=200": (5, 200)}
def main():
    res = {}; print(f"{'config':20s} {'no jammer':>10s} {'data jam':>9s} {'control jam':>12s}  (jammer duty: data {1.0:.2f}, control {1/20:.2f})")
    for n, (R, D) in CONFIGS.items():
        res[n] = {m: avg(R, D, m)["avail"] for m in ("none", "data", "control")}
        print(f"{n:20s} {res[n]['none']:10.3f} {res[n]['data']:9.3f} {res[n]['control']:12.3f}")
    fig, ax = plt.subplots(figsize=(6.2, 3.4)); x = np.arange(len(CONFIGS)); w = 0.27
    for i, (m, col) in enumerate((("none", C["grey"]), ("data", C["sky"]), ("control", C["verm"]))):
        ax.bar(x + (i - 1) * w, [res[n][m] for n in CONFIGS], w, color=col, label={"none": "no jammer", "data": "jam 1 data channel (100% duty)", "control": "jam beacons only (5% duty)"}[m])
    ax.set_xticks(x); ax.set_xticklabels(list(CONFIGS), fontsize=7); ax.set_ylabel("availability"); ax.legend(fontsize=7, loc="lower right"); ax.set_ylim(0, 1.05)
    ax.set_title("R3 control-plane jamming vs rendezvous design"); save_fig(fig, "r3_control_plane.png"); save_json("r3_control_plane.json", res)
    key("availability under beacon-only jamming, R=1 vs R=5/D=100", f"{res['R=1, D=60 (naive)']['control']:.3f} vs {res['R=5, D=100']['control']:.3f}")
    return res
if __name__ == "__main__": main()
