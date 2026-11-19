"""Adversary models against a hop schedule (own-link test models; nothing here transmits anything)."""
import numpy as np


def _lfsr_step(states):
    bit = ((states >> 0) ^ (states >> 2) ^ (states >> 3) ^ (states >> 5)) & 1
    return (states >> 1) | (bit << 15)


class LfsrBreaker:
    """Knows the generator (Kerckhoffs) but not the state. Keeps every state consistent with the hops seen so far.
    Once one candidate remains, predicts all future hops exactly."""
    def __init__(self, M):
        self.M = M
        self.cand = np.arange(1, 65536, dtype=np.uint32)   # all nonzero 16-bit states (before first step)
        self.seen = 0

    def observe(self, ch):
        self.cand = _lfsr_step(self.cand)
        self.cand = self.cand[(self.cand % self.M) == ch]
        self.seen += 1

    def predict(self, rng):
        if len(self.cand) == 1:
            return int(_lfsr_step(self.cand)[0] % self.M)
        if len(self.cand) > 1:  # vote among candidates
            nxt = _lfsr_step(self.cand) % self.M
            return int(np.bincount(nxt, minlength=self.M).argmax())
        return int(rng.integers(self.M))

    def identified(self):
        return len(self.cand) == 1


class FreqGuesser:
    """Generic statistical attacker: guesses the most frequently seen channel (works only on biased schedules)."""
    def __init__(self, M):
        self.M, self.cnt = M, np.zeros(M)

    def observe(self, ch):
        self.cnt[ch] += 1

    def predict(self, rng):
        m = self.cnt.max()
        return int(rng.choice(np.flatnonzero(self.cnt == m)))

    def identified(self):
        return False


def attack_run(schedule, M, attacker, slots=3000, p_jam=0.95, p_clean=0.01, epoch=None, make_schedule=None, seed=1):
    """Each slot the jammer predicts the channel from past hops, then jams its prediction.
    epoch/make_schedule: re-key every `epoch` slots (attacker knows the boundaries, so it restarts elimination)."""
    rng = np.random.default_rng(seed)
    h = np.array(schedule)
    delivered, ident_at = 0, None
    for t in range(slots):
        if epoch and make_schedule and t % epoch == 0:
            h[t:t + epoch] = make_schedule(epoch, t // epoch)[: len(h[t:t + epoch])]
            attacker = type(attacker)(M)
        guess = attacker.predict(rng)
        jam = guess == h[t]
        delivered += rng.random() > (p_jam if jam else p_clean)
        attacker.observe(int(h[t]))
        if ident_at is None and attacker.identified():
            ident_at = t + 1
    return delivered / slots, ident_at
