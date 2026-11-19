"""Idea 21: exhaustive state-space check of the hop-synchronisation protocol.
State = (offset, missed, mode, phase). offset: RX clock error in drift units, |offset| <= GUARD means a packet can be heard.
Each slot the environment may (nondeterministically) lose the packet; the offset drifts by 0 or +1 units (fixed-sign crystal drift: it cannot come back by itself).
v1 (what link_sim.py does): RX resets offset only by hearing a packet; nothing else.
v2: after MISS_MAX consecutive missed slots RX enters SEARCH: it parks on the rendezvous channel; TX sends a beacon there every
BEACON slots (phase counter); hearing a beacon resets offset to 0 and returns to SYNCED.
Property checked: from EVERY reachable state a SYNCED state with offset 0 is still reachable (no dead states), assuming losses are not permanent."""
from collections import deque

def explore(version, GUARD=2, MAXOFF=6, MISS_MAX=3, BEACON=4):
    def succ(st):
        off, miss, mode, ph = st; out = set()
        ph2 = (ph + 1) % BEACON
        for lost in (0, 1):
            for d in (0, 1):   # crystal drift has a fixed sign: the offset never drifts back by itself
                o = max(-MAXOFF, min(MAXOFF, off + d))
                if mode == "SYNC":
                    heard = (not lost) and abs(o) <= GUARD
                    if heard: out.add((0, 0, "SYNC", ph2))
                    else:
                        m = miss + 1
                        if version == 2 and m >= MISS_MAX: out.add((o, 0, "SEARCH", ph2))
                        else: out.add((o, min(m, MISS_MAX), "SYNC", ph2))
                else:  # SEARCH: only a beacon (phase 0) heard on the rendezvous channel (not lost) brings it back
                    if ph == 0 and not lost: out.add((0, 0, "SYNC", ph2))
                    else: out.add((o, 0, "SEARCH", ph2))
        return out
    start = {(o, 0, "SYNC", 0) for o in range(-GUARD, GUARD + 1)}
    seen, q, edges = set(start), deque(start), {}
    while q:
        s = q.popleft(); edges[s] = succ(s)
        for t in edges[s]:
            if t not in seen: seen.add(t); q.append(t)
    good = {s for s in seen if s[0] == 0 and s[2] == "SYNC"}
    rev = {}
    for s, ts in edges.items():
        for t in ts: rev.setdefault(t, set()).add(s)
    can = set(good); q = deque(good)
    while q:
        t = q.popleft()
        for s in rev.get(t, ()):
            if s not in can: can.add(s); q.append(s)
    dead = seen - can
    return len(seen), len(dead), sorted(dead)[:4]

if __name__ == "__main__":
    import json
    res = {}
    for v in (1, 2):
        n, d, ex = explore(v); res[f"v{v}"] = dict(states=n, dead_states=d, examples=[str(e) for e in ex])
        print(f"protocol v{v}: {n} reachable states, {d} dead states (cannot ever return to synchronised). examples: {ex}")
    for g in (1, 2, 3):
        print(f"v2 guard={g}: dead states = {explore(2, GUARD=g)[1]}")
    json.dump(res, open("figures/modelcheck.json", "w"), indent=1)
    assert res["v1"]["dead_states"] > 0 and res["v2"]["dead_states"] == 0
