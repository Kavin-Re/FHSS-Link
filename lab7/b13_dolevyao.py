"""Beyond #13: Dolev-Yao style exhaustive check of the safety-guard token protocol (simulation only; no emission, pure logic).
The attacker owns the network: it can drop, delay, reorder, replay and inject messages, and see every message, but cannot forge an HMAC
(forgery = random 8-byte tag, modelled by a 'forge' action that must be rejected).
We drive the REAL sim/safety.Guard (imported read-only) through every action sequence up to a depth bound and check:
  S1 (bounded staleness): an emission is allowed only if the owner issued the authorising token at most BOUND seconds earlier;
  S2 (no replay):         a token is never accepted twice;   S3 (no forgery): forged tags are never accepted.
The original protocol has no timestamp/nonce inside the token and freshness is judged at RECEIPT time, so a delayed delivery is a counterexample to S1.
Fix (lab7 ChallengeGuard): node-issued nonce, response valid for CTTL seconds after the challenge. Same exhaustive check on the fix."""
import copy
from _common import *
from safety import Guard

KEY = b"lab7-model-check-key"
TTL = 5.0          # Guard token_ttl_s default
CTTL = 2.0         # challenge validity of the fix
BOUND = TTL + CTTL # what we promise: authorisation never older than this
CH = 3             # an allowed channel

class ChallengeGuard(Guard):
    """Fix: the node issues a fresh nonce; the owner's response MAC covers (nonce, ctr); response must arrive within CTTL of the challenge."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.nonce, self.nonce_time, self.n_used = 0, -1e9, True
    def challenge(self, now):
        self.nonce += 1; self.nonce_time = now; self.n_used = False; return self.nonce
    @staticmethod
    def respond(key, nonce, ctr):
        import hmac, hashlib
        return hmac.new(key, nonce.to_bytes(8, "big") + ctr.to_bytes(8, "big"), hashlib.sha256).digest()[:8]
    def accept_response(self, now, nonce, ctr, tag):
        import hmac
        good = (nonce == self.nonce and not self.n_used and now - self.nonce_time <= CTTL and ctr > self.last_ctr
                and hmac.compare_digest(tag, self.respond(self.key, nonce, ctr)))
        if good: self.n_used = True; self.last_ctr = ctr; self.token_time = now
        self.log.append((now, "token", "accepted" if good else "REJECTED")); return good

class World:
    """One protocol run: guard + attacker network state + ground truth (when the owner actually issued tokens)."""
    def __init__(self, variant):
        self.v, self.now = variant, 0.0
        self.g = (Guard if variant == "original" else ChallengeGuard)(KEY, {CH}, max_power=1, max_duty=1.0, max_burst_s=10**6, token_ttl_s=TTL)
        self.ctr = 0; self.issued = []; self.accepted_ctrs = []; self.auth_issue_time = None; self.viol = None
        self.chal = None          # (nonce, time) last challenge seen by the network
    def step(self, act):
        a = act[0]
        if a == "tick": self.now += act[1]
        elif a == "owner_issue":                        # original protocol: owner mints a token (ctr, tag) and sends it into the network
            self.ctr += 1; _, tag = Guard.make_token(KEY, self.ctr); self.issued.append((self.ctr, tag, self.now))
        elif a == "challenge":                          # fix: node emits a nonce
            n = self.g.challenge(self.now); self.chal = (n, self.now)
        elif a == "owner_respond":                      # fix: owner answers the latest challenge it has seen
            if self.chal:
                self.ctr += 1; n = self.chal[0]
                self.issued.append((self.ctr, (n, ChallengeGuard.respond(KEY, n, self.ctr)), self.now))
        elif a == "deliver":                            # attacker (or network) delivers issued message #j, possibly late or again
            j = act[1]
            if j < len(self.issued):
                ctr, tag, t_issue = self.issued[j]
                if self.v == "original": ok = self.g.accept_token(self.now, ctr, tag)
                else: ok = self.g.accept_response(self.now, tag[0], ctr, tag[1])
                if ok:
                    if ctr in self.accepted_ctrs: self.viol = ("S2 replay accepted", ctr)
                    self.accepted_ctrs.append(ctr); self.auth_issue_time = t_issue
        elif a == "forge":                              # injected message with a guessed tag
            fake = bytes(8)
            ok = self.g.accept_token(self.now, 10**6, fake) if self.v == "original" else self.g.accept_response(self.now, self.g.nonce, 10**6, fake)
            if ok: self.viol = ("S3 forged tag accepted", None)
        elif a == "request":
            allowed, why = self.g.request(self.now, CH, 1, dt=0.1)
            if allowed:
                if self.auth_issue_time is None or self.now - self.auth_issue_time > BOUND + 1e-9:
                    stale = None if self.auth_issue_time is None else self.now - self.auth_issue_time
                    self.viol = ("S1 emission on authorisation issued %s s ago (bound %.0f s)" % (stale, BOUND), stale)

def actions(variant, n_issued_cap=2):
    base = [("tick", 1.0), ("tick", 4.0), ("forge",), ("request",)]
    if variant == "original": base += [("owner_issue",)] + [("deliver", j) for j in range(n_issued_cap)]
    else: base += [("challenge",), ("owner_respond",)] + [("deliver", j) for j in range(n_issued_cap)]
    return base

def explore(variant, depth):
    """Exhaustive DFS over all action sequences up to `depth` (replaying the real Guard); returns (#sequences, first violation trace per kind)."""
    acts = actions(variant); n = 0; found = {}
    stack = [()]
    while stack:
        seq = stack.pop()
        if len(seq) == depth: continue
        for a in acts:
            s2 = seq + (a,); n += 1
            w = World(variant)
            for x in s2:
                w.step(x)
                if w.viol: break
            if w.viol:
                kind = w.viol[0].split()[0]
                if kind not in found or len(s2) < len(found[kind][0]): found[kind] = (s2, w.viol)
                continue                      # do not extend a violating trace
            stack.append(s2)
    return n, found

def run(fast=False):
    depth = 5 if fast else 6
    out = {}
    for v in ("original", "challenge"):
        n, found = explore(v, depth)
        out[v] = dict(depth=depth, sequences=n, violations={k: dict(trace=[list(x) for x in t], what=list(w)) for k, (t, w) in found.items()})
    return out

def main():
    out = run()
    for v, r in out.items():
        print(f"[{v}] depth {r['depth']}: {r['sequences']} action sequences checked on the real guard; violations: {sorted(r['violations']) or 'none'}")
        for k, d in r["violations"].items(): print("   counterexample", k, d["trace"], "->", d["what"][0])
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    # draw the shortest S1 counterexample as a timeline
    ce = out["original"]["violations"].get("S1")
    ax.set_xlim(-1, 14); ax.set_ylim(0, 4); ax.set_yticks([1, 2, 3]); ax.set_yticklabels(["node: emits", "attacker: delivers", "owner: issues token"])
    t = 0.0; ev = []
    if ce:
        for a in ce["trace"]:
            if a[0] == "tick": t += a[1]
            else: ev.append((t, a[0]))
        ymap = {"owner_issue": 3, "deliver": 2, "request": 1, "forge": 2}
        for tt, nm in ev:
            ax.plot(tt, ymap.get(nm, 2), "o", color=C["verm"] if nm == "request" else C["blue"], ms=9); ax.text(tt, ymap.get(nm, 2) + 0.25, nm, ha="center", fontsize=8)
        issue_t = [tt for tt, nm in ev if nm == "owner_issue"][0]
        ax.annotate("", xy=(ev[-1][0], 3.0), xytext=(issue_t, 3.0), arrowprops=dict(arrowstyle="<->", color=C["grey"]))
        ax.text((issue_t + ev[-1][0]) / 2, 3.35, f"token age at emission {ev[-1][0]-issue_t:.0f} s > bound {BOUND:.0f} s", ha="center", color=C["verm"])
    ax.set_xlabel("time (s)"); ax.set_title("original Guard: shortest counterexample found by exhaustive search (delayed delivery)")
    ax.grid(axis="y", alpha=0)
    save_fig(fig, "b13_dolevyao.png"); save_json("b13_dolevyao.json", out)
    o, c = out["original"], out["challenge"]
    key("B13", f"{o['sequences']} sequences (depth {o['depth']}) on the real Guard: original violates {sorted(o['violations'])} (shortest S1 trace length {len(o['violations']['S1']['trace']) if 'S1' in o['violations'] else '-'}); challenge-response fix: {sorted(c['violations']) or 'no violations'} over {c['sequences']} sequences; forged/replayed tokens never accepted")
if __name__ == "__main__":
    main()
