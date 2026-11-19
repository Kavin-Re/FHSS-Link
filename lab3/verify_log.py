#!/usr/bin/env python3
"""Command-line verifier for lab3 hash-chain decision logs (see hashchain.py for the model and its limits).
usage: python3 verify_log.py LOG.jsonl [--key-hex HEX | --key-env VAR | --key-file FILE] [--head HEX] [--count N]
Exit status: 0 = chain and Merkle roots consistent, 1 = tampering/inconsistency detected, 2 = usage or unreadable file.
Integrity only: plain sha256 logs can be rewritten consistently by anyone; use an HMAC log with the key, or an anchored --head/--count."""
import argparse, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hashchain


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"); g = ap.add_mutually_exclusive_group()
    g.add_argument("--key-hex"); g.add_argument("--key-env"); g.add_argument("--key-file")
    ap.add_argument("--head", help="anchored head hash (hex) the chain must end with"); ap.add_argument("--count", type=int, help="anchored record count")
    a = ap.parse_args(argv); key = None
    try:
        if a.key_hex: key = bytes.fromhex(a.key_hex)
        elif a.key_env: key = os.environ[a.key_env].encode()
        elif a.key_file: key = open(a.key_file, "rb").read().strip()
        lines = hashchain.read_lines(a.log)
    except (OSError, ValueError, KeyError) as e:
        print(f"cannot read input: {e}", file=sys.stderr); return 2
    if lines and lines[0].get('mode') == 'hmac-sha256' and key is None:
        print('this log is hmac-sha256: give --key-hex/--key-env/--key-file', file=sys.stderr); return 2
    r = hashchain.verify(lines, key=key, head=a.head, count=a.count)
    print(f"records={r['n_records']} blocks={r['n_blocks']} head={r['head']}")
    if r["ok"]: print("OK: no inconsistency found (integrity only, see docs)"); return 0
    print(f"TAMPERING DETECTED: first flagged record index = {r['first_bad']}")
    for i, txt in r["problems"][:20]: print(f"  record {i}: {txt}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
