"""Idea 20: energy-depletion attack. A jammer that corrupts a fraction of slots forces retries; a battery node dies faster.
Per-slot energy: TX attempt = 1.0 unit, listening for ACK = 0.3, sleep = 0.01. A node must deliver one packet every slot-period.
Policies: naive (retry up to R times at once), backoff (retry only if the last attempt failed, then sleep 2^i slots, cap), and
classifier-driven sleep-and-probe (when loss > 60% over the last 20 attempts, probe once every 10 slots)."""
import numpy as np

def run(policy, p_loss, packets=3000, R=5, seed=1):
    rng = np.random.default_rng(seed); E = 0.0; delivered = 0; hist = []; slots = 0
    for _ in range(packets):
        att = 0; ok = False
        while att < R:
            if policy == "probe" and len(hist) >= 20 and np.mean(hist[-20:]) > 0.6 and att >= 1:
                E += 0.01 * 10; slots += 10; break    # sleep 10 slots, then drop this retry
            att += 1; E += 1.3; slots += 1; l = rng.random() < p_loss; hist.append(l)
            if not l: ok = True; break
            if policy in ("backoff", "probe"): E += 0.01 * (2 ** min(att, 4)); slots += 2 ** min(att, 4)
        delivered += ok
    return dict(energy_per_delivered=E / max(delivered, 1), drain_per_packet_period=E / packets, pdr=delivered / packets)

if __name__ == "__main__":
    import json; res = {}
    print("p_loss | battery drain per packet period (delivery ratio): naive | backoff | probe")
    for p in (0.0, 0.2, 0.5, 0.8, 0.95):
        row = {pol: run(pol, p) for pol in ("naive", "backoff", "probe")}; res[str(p)] = row
        print(f"{p:5.2f} | " + " | ".join(f"{row[k]['drain_per_packet_period']:6.2f} ({row[k]['pdr']:.2f})" for k in row))
    json.dump(res, open("figures/energy.json", "w"), indent=1)
