"""Idea 23: digital twin from a measured log. 'Real' environment (hidden from the twin): 13 channels where Wi-Fi channels 1, 6, 11 are busy
(bursty on/off traffic, loss 0.6 while on) and their neighbours leak a little. We record a log with the blind policy through the serial format,
fit per-channel loss rates from the log only, then predict the delivery of other policies on the fitted twin and compare with the real runs."""
import numpy as np
from adaptive import make_policy
from serial_proto import encode, parse

class RealEnv:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed); self.on = np.zeros(13, bool); self.busy = {0, 5, 10}
    def loss(self, c, t):
        if t % 20 == 0:
            for b in self.busy: self.on[b] = self.rng.random() < 0.5          # bursty Wi-Fi: re-drawn every 20 slots
        p = 0.02
        if c in self.busy and self.on[c]: p = 0.6
        elif any(abs(c - b) == 1 and self.on[b] for b in self.busy): p = 0.12
        return p

def run(policy, env_factory, slots=12000, seed=1, record=False):
    env = env_factory(seed); pol = make_policy(policy, 13, np.random.default_rng(seed + 9)); rng = np.random.default_rng(seed + 3); ok_all = []; lines = []
    for t in range(slots):
        c = pol.pick(); ok = rng.random() > env.loss(c, t); pol.update(c, float(ok)); ok_all.append(ok)
        if record: lines.append(encode(t, c, ok, 0 if ok else 1, -60))
    return float(np.mean(ok_all)), lines

class Twin:
    """Static per-channel Bernoulli model fitted from parsed log lines (no knowledge of Wi-Fi structure)."""
    def __init__(self, lines):
        n = np.zeros(13); l = np.zeros(13)
        for ln in lines:
            r = parse(ln); n[r["ch"]] += 1; l[r["ch"]] += (not r["ok"])
        self.p = (l + 1) / (n + 2)
    def loss(self, c, t): return float(self.p[c])

if __name__ == "__main__":
    import json; res = {}
    real = lambda s: RealEnv(s)
    _, log = run("blind", real, seed=1, record=True)
    twin = Twin(log); print("fitted loss per channel from a 12,000-slot blind-hop log:", np.round(twin.p, 2).tolist())
    print("policy | real (3 seeds) | twin prediction | error (points)")
    for pol in ("blind", "afh", "thompson", "mixed"):
        r = np.mean([run(pol, real, seed=s)[0] for s in (11, 12, 13)]); p = np.mean([run(pol, lambda s: twin, seed=s)[0] for s in (11, 12, 13)])
        res[pol] = dict(real=float(r), twin=float(p), error_points=float((p - r) * 100)); print(f"{pol:9s} | {r:.3f} | {p:.3f} | {100*(p-r):+.1f}")
    json.dump(res, open("figures/twin.json", "w"), indent=1)
