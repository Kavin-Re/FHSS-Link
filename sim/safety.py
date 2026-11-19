"""Idea 27: safety guard for the interference test node (policy logic, testable now; the same rules go into firmware later).
The node may emit ONLY if every rule passes, and every decision is logged:
 1. authorisation: a fresh authenticated 'test window open' token from the owner's TX board (HMAC over a counter, valid 5 s)
 2. channel in the allowed own-link set  3. power level <= cap (level 0 = lowest)  4. duty cycle <= limit over a sliding 10 s window
 5. continuous emission <= 2 s  6. kill switch / loss of token stops emission within one slot."""
import hmac, hashlib

class Guard:
    def __init__(self, key, allowed_channels, max_power=1, max_duty=0.10, max_burst_s=2.0, token_ttl_s=5.0):
        self.key, self.allowed, self.maxp, self.maxd, self.maxb, self.ttl = key, set(allowed_channels), max_power, max_duty, max_burst_s, token_ttl_s
        self.last_ctr, self.token_time, self.on_log, self.killed, self.burst, self.log = -1, -1e9, [], False, 0.0, []

    @staticmethod
    def make_token(key, ctr): return ctr, hmac.new(key, ctr.to_bytes(8, "big"), hashlib.sha256).digest()[:8]

    def accept_token(self, now, ctr, tag):
        ok = ctr > self.last_ctr and hmac.compare_digest(tag, hmac.new(self.key, ctr.to_bytes(8, "big"), hashlib.sha256).digest()[:8])
        if ok: self.last_ctr, self.token_time = ctr, now
        self.log.append((now, "token", "accepted" if ok else "REJECTED (bad tag or replay)")); return ok

    def kill(self, now): self.killed = True; self.log.append((now, "kill", "kill switch pressed"))

    def request(self, now, channel, power, dt=0.1):
        """Ask to emit for dt seconds on channel at power level. Returns (allowed, reason)."""
        why = None
        if self.killed: why = "kill switch active"
        elif now - self.token_time > self.ttl: why = "no valid token (expired or never received)"
        elif channel not in self.allowed: why = f"channel {channel} not in the own-link set"
        elif power > self.maxp: why = f"power level {power} above cap {self.maxp}"
        else:
            self.on_log = [(t, d) for t, d in self.on_log if now - t < 10.0]
            duty = (sum(d for _, d in self.on_log) + dt) / 10.0
            if duty > self.maxd: why = f"duty cycle {duty:.0%} would exceed {self.maxd:.0%}"
            elif self.burst + dt > self.maxb: why = "continuous burst limit reached"
        if why: self.burst = 0.0; self.log.append((now, "deny", why)); return False, why
        self.on_log.append((now, dt)); self.burst += dt; self.log.append((now, "allow", f"ch {channel}, level {power}, {dt}s")); return True, "ok"
