"""Figures: adaptive jammer vs LFSR schedule and vs keyed PRF schedule."""
import numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from schedule import lfsr_schedule, prf_schedule
from attack import LfsrBreaker, attack_run

M = 13
# 1. hops needed to identify the LFSR state (500 random keys, several M)
plt.figure()
for m in (8, 13, 16, 32):
    ids = [attack_run(lfsr_schedule(120, m, key=k), m, LfsrBreaker(m), slots=120)[1] or 120 for k in range(1, 501, 5)]
    plt.hist(ids, bins=range(0, 40), alpha=.55, label=f"M={m} (mean {np.mean(ids):.1f})")
plt.xlabel("observed hops until the jammer knows the whole schedule"); plt.ylabel("keys (of 100)")
plt.title("LFSR hop schedule: state recovered after a handful of hops"); plt.legend(); plt.grid(alpha=.3)
plt.savefig("figures/8_lfsr_break.png", dpi=130); plt.close()

# 2. rolling PDR under the adaptive jammer
def rolling(sched, n=600, w=25):
    rng = np.random.default_rng(3); att = LfsrBreaker(M); ok = []
    for t in range(n):
        g = att.predict(rng); jam = g == sched[t]
        ok.append(rng.random() > (0.95 if jam else 0.01)); att.observe(int(sched[t]))
    return np.convolve(ok, np.ones(w) / w, mode="valid")
plt.figure()
plt.plot(rolling(lfsr_schedule(600, M)), label="LFSR schedule")
plt.plot(rolling(prf_schedule(600, M)), label="keyed PRF schedule (HMAC-SHA256)")
plt.xlabel("slot"); plt.ylabel("packet delivery (25-slot window)"); plt.ylim(0, 1.05); plt.grid(alpha=.3); plt.legend()
plt.title("Same adaptive jammer, two hop schedules"); plt.savefig("figures/9_adaptive_jammer.png", dpi=130); plt.close()
print("ok")
