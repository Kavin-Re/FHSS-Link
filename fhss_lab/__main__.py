"""Command line: python -m fhss_lab {run,emulate,classify,bench} ..."""
import argparse, os, subprocess, sys, time
from pathlib import Path
import fhss_lab


def cmd_run(a):
    print(f"BER (Monte Carlo, Eb/N0 = {a.ebn0} dB, {a.nbits} bits, FH M={a.M}, DS Gp={a.gp}) vs tone-jammer JSR")
    print(f"{'JSR dB':>7s} {'fixed':>10s} {'FH':>10s} {'DS':>10s}")
    for j, f, h, d in fhss_lab.ber_table(a.ebn0, tuple(float(x) for x in a.jsr.split(",")), a.nbits, a.M, a.gp): print(f"{j:7.1f} {f:10.5f} {h:10.5f} {d:10.5f}")
    print(f"\nPacket delivery ratio (theory, one jammed channel, JSR 10 dB, 256-bit packets)")
    for M, p in fhss_lab.pdr_table(ebn0_db=a.ebn0): print(f"  M={M:3d}: PDR {p:.4f}")
    return 0


def cmd_emulate(a):
    n = 0; out = open(a.out, "w") if a.out != "-" else sys.stdout
    try:
        for line in fhss_lab.emulate(a.defender, a.jammer, a.slots, a.M, a.seed): out.write(line); n += 1
    finally:
        if out is not sys.stdout: out.close()
    print(f"wrote {n} serial lines to {a.out}", file=sys.stderr if a.out == "-" else sys.stdout); return 0


def cmd_classify(a):
    t = time.time(); r = fhss_lab.classifier_accuracy(a.train, a.test, a.seed)
    print(f"rule-based accuracy {r['rule']:.3f}; softmax accuracy {r['softmax']:.3f} on {r['n_test']} simulated test windows ({a.train} train windows per class, {time.time()-t:.1f} s)"); return 0


def cmd_bench(a):
    sim = fhss_lab.sim_dir(); names = a.only or ["test_sim.py", "test_link.py", "test_attack.py", "test_fec.py", "test_proto.py", "test_safety.py", "modelcheck.py"]
    bad = 0
    for n in names:
        t = time.time(); p = subprocess.run([sys.executable, n], cwd=sim, capture_output=True, text=True); last = (p.stdout.strip().splitlines() or [""])[-1]
        print(f"{'ok  ' if p.returncode == 0 else 'FAIL'} {n:16s} {time.time()-t:6.1f}s  {last}"); bad += p.returncode != 0
        if p.returncode != 0: print(p.stderr[-500:])
    if a.lab3:
        t = time.time(); p = subprocess.run([sys.executable, str(sim.parent / "lab3" / "test_batchC.py")], capture_output=True, text=True); print(f"{'ok  ' if p.returncode == 0 else 'FAIL'} lab3/test_batchC.py {time.time()-t:6.1f}s  {(p.stdout.strip().splitlines() or [''])[-1]}"); bad += p.returncode != 0
    print("ALL PASSED" if not bad else f"{bad} FAILED"); return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fhss_lab", description="FHSS-Link lab tools (wrappers around the simulators in sim/)"); ap.add_argument("--version", action="version", version=fhss_lab.__version__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run", help="BER / PDR table (fixed vs FH vs DS under a tone jammer)"); r.add_argument("--ebn0", type=float, default=10.0); r.add_argument("--jsr", default="0,10,20"); r.add_argument("--nbits", type=int, default=100000); r.add_argument("--M", type=int, default=13); r.add_argument("--gp", type=int, default=32); r.set_defaults(f=cmd_run)
    e = sp.add_parser("emulate", help="write a serial-format log from the emulated board"); e.add_argument("--defender", default="blind"); e.add_argument("--jammer", default="static"); e.add_argument("--slots", type=int, default=3000); e.add_argument("--M", type=int, default=13); e.add_argument("--seed", type=int, default=1); e.add_argument("--out", default="fhss_emulated.log", help="file or - for stdout"); e.set_defaults(f=cmd_emulate)
    c = sp.add_parser("classify", help="quick jammer-classifier accuracy"); c.add_argument("--train", type=int, default=40, help="train windows per class"); c.add_argument("--test", type=int, default=30, help="test windows per class"); c.add_argument("--seed", type=int, default=0); c.set_defaults(f=cmd_classify)
    b = sp.add_parser("bench", help="run the sim/ test scripts (same list as run_tests.sh, but with real exit codes)"); b.add_argument("--only", nargs="*", help="run only these test files from sim/"); b.add_argument("--lab3", action="store_true", help="also run lab3/test_batchC.py (slow)"); b.set_defaults(f=cmd_bench)
    a = ap.parse_args(argv); return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
