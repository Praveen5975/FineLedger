from __future__ import annotations

import argparse
import sys
from datetime import date

from .ledger import Ledger, LedgerError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fineledger", description="Countersigned fine-gold ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="run the end-to-end scenario")
    v = sub.add_parser("verify", help="verify the hash chain of a ledger file")
    v.add_argument("path")
    s = sub.add_parser("serve", help="serve the API on a DEMO ledger (demo keys, not for production)")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        from .demo import main as demo
        return demo()
    if a.cmd == "verify":
        import os
        if not os.path.isfile(a.path):
            print(f"cannot read {a.path}: no such file")
            return 2
        try:
            L = Ledger(a.path, verify_on_load=False)
        except Exception as e:  # unreadable file
            print(f"cannot read {a.path}: {e}")
            return 2
        if not L.records:
            print(f"cannot verify {a.path}: file contains no records")
            return 2
        ok, err = L.verify()
        print(f"OK: {len(L.records)} records, chain intact" if ok else f"FAILED: {err}")
        return 0 if ok else 1
    if a.cmd == "serve":
        import uvicorn
        from .api import create_app
        from .demo import KEYS, build_scenario
        L = build_scenario(date.today())
        print("DEMO keys (header X-Party-Id / X-Party-Key):", KEYS)
        uvicorn.run(create_app(L, KEYS), host="127.0.0.1", port=a.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
