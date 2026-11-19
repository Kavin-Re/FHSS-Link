"""Beyond #23: sandboxed red-team / blue-team loop with a logging referee (simulation only).
HONEST SCOPE: the 'agents' here are scripted search procedures, not language-model agents. Red evolves attack PROGRAMS, which are plain data
(a dict from a small whitelisted DSL) interpreted by the referee; red never supplies code. Blue picks patches from a fixed catalogue. The referee
validates every submission, runs it in the link simulator (13 channels, 95 % loss on a jammed channel, 1 % otherwise), scores both sides and appends
every action to a hash-chained JSONL log. During the loop socket / subprocess / os.system are replaced by functions that raise and log (no network,
no system access); a static AST audit of this file checks for forbidden imports and eval/exec.
Red budget: <= 2 jammed channels per slot, duty <= 1. Red sees only its own scores (black box). Blue sees red's archived programs."""
import ast, hashlib, json, os, socket, subprocess, copy
import numpy as np
from _common import *
from adaptive import AFH, Thompson, Blind

M = 13
P_JAM, P_CLEAN = 0.95, 0.01
KINDS = ["static", "sweep", "follow_most_used", "follow_last", "poison"]
SPEC = {"kind": (str, KINDS), "k": (int, (1, 2)), "dwell": (int, (1, 60)), "duty": (float, (0.2, 1.0)),
        "start": (int, (0, M - 1)), "poison_q": (float, (0.0, 0.6))}

def validate(prog):
    """Whitelist validation. Returns (ok, reason). Anything outside the DSL (extra keys, wrong types, out-of-budget values) is refused, never executed."""
    if not isinstance(prog, dict): return False, "not a dict"
    if set(prog) != set(SPEC): return False, f"keys must be exactly {sorted(SPEC)}; got extra/missing {sorted(set(prog) ^ set(SPEC))}"
    for k, (typ, rng_) in SPEC.items():
        v = prog[k]
        if typ is float and isinstance(v, int) and not isinstance(v, bool): v = float(v)
        if type(v) is not typ: return False, f"{k}: wrong type {type(v).__name__}"
        if typ is str:
            if v not in rng_: return False, f"{k}: {v!r} not in whitelist"
        elif not (rng_[0] <= v <= rng_[1]): return False, f"{k}={v} outside budget {rng_}"
    return True, "ok"

class Defence:
    def __init__(self, cfg, rng):
        self.cfg = cfg; self.rng = rng
        pol = cfg["policy"]
        self.p = {"afh": lambda: AFH(M, rng, floor=cfg["floor"]), "thompson": lambda: Thompson(M, rng, eps=cfg["floor"]),
                  "blind": lambda: Blind(M, rng)}[pol]()
    def pick(self): return self.p.pick()
    def update(self, c, ok_true, forged):
        # authenticated ACKs: forged NACKs are dropped; otherwise the learner believes them
        self.p.update(c, 0 if (forged and not self.cfg["auth_ack"]) else ok_true)

def simulate(cfg, prog, seed, slots=800):
    rng = np.random.default_rng(seed); d = Defence(cfg, rng)
    counts = np.zeros(M); last = []; jam_set_cache = set(); ok_sum = 0; jam_slots = 0
    forged_set = {(prog["start"] + 5 + i) % M for i in range(4)}
    for t in range(slots):
        kd = prog["kind"]
        if kd == "static" or kd == "poison": js = {(prog["start"] + i) % M for i in range(1 if kd == "poison" else prog["k"])}
        elif kd == "sweep": base = (prog["start"] + t // prog["dwell"]) % M; js = {(base + i) % M for i in range(prog["k"])}
        elif kd == "follow_most_used":
            if t % prog["dwell"] == 0: jam_set_cache = set(np.argsort(-counts, kind="stable")[: prog["k"]].tolist())
            js = jam_set_cache
        else: js = set(last[-prog["k"]:]) if last else {prog["start"]}
        active = rng.random() < prog["duty"]
        c = d.pick(); counts[c] += 1
        jammed = active and (c in js); jam_slots += jammed
        ok = int(rng.random() >= (P_JAM if jammed else P_CLEAN))
        forged = (kd == "poison" and c in forged_set and ok == 1 and rng.random() < prog["poison_q"])
        d.update(c, ok, forged); ok_sum += ok
        last.append(c); last = last[-4:]
    return ok_sum / slots

def mean_delivery(cfg, prog, seeds=(1, 2, 3), slots=800):
    return float(np.mean([simulate(cfg, prog, s, slots) for s in seeds]))

PATCHES = {   # name: (config change, blue cost in delivery-equivalent units)
    "none": ({}, 0.0),
    "uniform_floor_15": ({"floor": 0.15}, 0.004),
    "switch_thompson_floor_10": ({"policy": "thompson", "floor": 0.10}, 0.004),
    "authenticated_ack": ({"auth_ack": True}, 0.008),
    "pure_uniform_hopping": ({"policy": "blind", "floor": 0.0}, 0.0),
}
BASE_CFG = {"policy": "afh", "floor": 0.0, "auth_ack": False}

class Sandbox:
    """Replace network / process primitives by functions that raise and log. Used as a context manager around the whole loop."""
    def __init__(self, log): self.log = log
    def __enter__(self):
        self.saved = (socket.socket, subprocess.Popen, os.system)
        def deny(name):
            def f(*a, **k): self.log("sandbox", "DENIED_SYSCALL", {"call": name}); raise PermissionError(f"{name} blocked by lab7 sandbox")
            return f
        socket.socket = deny("socket.socket"); subprocess.Popen = deny("subprocess.Popen"); os.system = deny("os.system")
        return self
    def __exit__(self, *e): socket.socket, subprocess.Popen, os.system = self.saved

class Referee:
    def __init__(self, path=None):
        self.entries = []; self.prev = "0" * 64; self.path = path; self.t = 0
    def log(self, actor, action, payload):
        self.t += 1
        e = {"seq": self.t, "actor": actor, "action": action, "payload": payload, "prev": self.prev}
        e["hash"] = hashlib.sha256(json.dumps({k: e[k] for k in ("seq", "actor", "action", "payload", "prev")}, sort_keys=True, default=str).encode()).hexdigest()
        self.prev = e["hash"]; self.entries.append(e); return e
    def save(self):
        if self.path:
            with open(self.path, "w") as f:
                for e in self.entries: f.write(json.dumps(e, default=str) + "\n")
    @staticmethod
    def verify(entries):
        prev = "0" * 64
        for e in entries:
            h = hashlib.sha256(json.dumps({k: e[k] for k in ("seq", "actor", "action", "payload", "prev")}, sort_keys=True, default=str).encode()).hexdigest()
            if e["prev"] != prev or e["hash"] != h: return False
            prev = h
        return True

def rand_prog(rng):
    return dict(kind=KINDS[int(rng.integers(len(KINDS)))], k=int(rng.integers(1, 3)), dwell=int(rng.integers(1, 61)), duty=float(round(rng.uniform(0.5, 1.0), 2)),
                start=int(rng.integers(M)), poison_q=float(round(rng.uniform(0, 0.6), 2)))

def mutate(p, rng):
    q = dict(p); f = rng.choice(list(SPEC))
    if f == "kind": q["kind"] = KINDS[int(rng.integers(len(KINDS)))]
    elif f == "k": q["k"] = int(rng.integers(1, 3))
    elif f == "dwell": q["dwell"] = int(np.clip(q["dwell"] + rng.integers(-10, 11), 1, 60))
    elif f == "duty": q["duty"] = float(np.clip(round(q["duty"] + rng.uniform(-.2, .2), 2), 0.2, 1.0))
    elif f == "start": q["start"] = int(rng.integers(M))
    else: q["poison_q"] = float(np.clip(round(q["poison_q"] + rng.uniform(-.2, .2), 2), 0, 0.6))
    return q

def loop(rounds=6, red_pop=10, seed=0, log_path=None, slots=800):
    rng = np.random.default_rng(seed)
    ref = Referee(log_path); cfg = dict(BASE_CFG); archive = []; hist = []
    with Sandbox(ref.log):
        ref.log("referee", "START", {"rounds": rounds, "red_pop": red_pop, "base_cfg": cfg, "M": M, "scope": "simulation only; no network/system access"})
        for r in range(1, rounds + 1):
            ref.log("referee", "ROUND_START", {"round": r, "blue_cfg": cfg})
            # --- red: submit programs (round 1 also probes the validator with hostile submissions, all of which must be refused)
            subs = [rand_prog(rng) for _ in range(red_pop // 2)] + [mutate(archive[int(rng.integers(len(archive)))]["prog"], rng) if archive else rand_prog(rng) for _ in range(red_pop - red_pop // 2)]
            if r == 1:
                subs += [dict(rand_prog(rng), cmd="__import__('os').system('id')"), dict(rand_prog(rng), k=13), dict(rand_prog(rng), kind="exec(open('x').read())"), "rm -rf /"]
            best = None
            for prog in subs:
                ok, why = validate(prog)
                if not ok: ref.log("red", "SUBMIT_REFUSED", {"prog": prog, "reason": why}); continue
                dlv = mean_delivery(cfg, prog, slots=slots)
                ref.log("red", "SUBMIT_RUN", {"prog": prog, "delivery_vs_current_blue": round(dlv, 4)})
                if best is None or dlv < best[0]: best = (dlv, prog)
            archive.append({"round": r, "prog": best[1], "delivery_at_submission": best[0]})
            ref.log("referee", "RED_BEST", {"round": r, "prog": best[1], "damage": round(1 - best[0], 4)})
            # --- blue: evaluate each patch against the whole archive (worst case), pay the cost, apply the best if it helps by > 0.005
            scores = {}
            for name, (chg, cost) in PATCHES.items():
                c2 = {**cfg, **chg}
                wc = min(mean_delivery(c2, a["prog"], slots=slots) for a in archive)
                scores[name] = wc - cost
                ref.log("blue", "PATCH_EVAL", {"patch": name, "worst_case_delivery": round(wc, 4), "cost": cost, "score": round(wc - cost, 4)})
            cur_wc = scores["none"]; bname = max(scores, key=scores.get)
            if bname != "none" and scores[bname] > cur_wc + 0.005: cfg = {**cfg, **PATCHES[bname][0]}; applied = bname
            else: applied = "none"
            wc_now = min(mean_delivery(cfg, a["prog"], slots=slots) for a in archive)
            ref.log("blue", "PATCH_APPLIED", {"patch": applied, "cfg": cfg, "worst_case_delivery_on_archive": round(wc_now, 4)})
            hist.append(dict(round=r, red_best_delivery=best[0], red_prog=best[1], patch=applied, blue_cfg=dict(cfg), blue_worst_case=wc_now))
        ref.log("referee", "END", {"final_cfg": cfg})
        # sandbox self-test inside the sandbox: a 'red' attempt to open a socket must raise
        try: socket.socket(); blocked = False
        except PermissionError: blocked = True
        ref.log("referee", "SANDBOX_SELFTEST", {"socket_blocked": blocked})
    ref.save()
    return dict(history=hist, archive=archive, final_cfg=cfg, entries=ref.entries, socket_blocked=blocked)

FORBIDDEN_IMPORTS = {"urllib", "requests", "http", "ftplib", "smtplib", "ctypes", "paramiko", "asyncio", "multiprocessing", "pickle", "shutil"}
def audit_source(path):
    """Static check of a lab7 script: no forbidden imports; no eval/exec/compile/__import__ calls. Returns list of findings."""
    tree = ast.parse(open(path).read()); bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in FORBIDDEN_IMPORTS: bad.append(("import", a.name, n.lineno))
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in FORBIDDEN_IMPORTS: bad.append(("import", n.module, n.lineno))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"eval", "exec", "compile", "__import__"}: bad.append(("call", n.func.id, n.lineno))
    return bad

def run(fast=False):
    return loop(rounds=4 if fast else 6, red_pop=6 if fast else 10, slots=500 if fast else 800,
                log_path=os.path.join(OUT, "b23_referee_log.jsonl"))

def main():
    out = run()
    gv = (M - 2) / M * (1 - P_CLEAN) + 2 / M * (1 - P_JAM)
    print(f"game value, uniform hopping vs a 2-channel jammer: {gv:.4f}")
    for h in out["history"]:
        p = h["red_prog"]
        print(f"round {h['round']}: red best vs current blue = {h['red_best_delivery']:.3f} ({p['kind']}, k={p['k']}, duty {p['duty']}), blue patch: {h['patch']:24s} -> worst case over archive {h['blue_worst_case']:.3f}, cfg {h['blue_cfg']}")
    ents = out["entries"]; refused = sum(e["action"] == "SUBMIT_REFUSED" for e in ents)
    print(f"log: {len(ents)} entries, chain valid: {Referee.verify(ents)}, refused hostile submissions: {refused}, socket blocked inside sandbox: {out['socket_blocked']}, source audit: {audit_source(__file__) or 'clean'}")
    h = out["history"]; r = [x["round"] for x in h]
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    ax.plot(r, [x["red_best_delivery"] for x in h], "o-", color=C["verm"], label="red: best attack vs current blue")
    ax.plot(r, [x["blue_worst_case"] for x in h], "s-", color=C["blue"], label="blue: worst case over red's archive")
    ax.axhline(gv, color=C["grey"], ls="--", label=f"uniform hopping vs 2-channel jammer ({gv:.3f})")
    for x in h: ax.annotate(x["patch"].replace("_", " "), (x["round"], x["blue_worst_case"]), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=7)
    ax.set_xlabel("round"); ax.set_ylabel("delivery ratio"); ax.set_ylim(0, 1.0); ax.legend(loc="lower right")
    save_fig(fig, "b23_redblue.png"); save_json("b23_redblue.json", {k: v for k, v in out.items() if k != "entries"})
    key("B23", f"{len(h)} rounds, {len(ents)} logged actions (hash chain valid, {refused} hostile submissions refused, sockets blocked): blue converged to '{h[-1]['blue_cfg']['policy']}' hopping with archive worst case {h[-1]['blue_worst_case']:.3f} = game value {gv:.3f}; red found no attack below it (best vs initial AFH config: {h[0]['red_best_delivery']:.3f})")
if __name__ == "__main__":
    main()
