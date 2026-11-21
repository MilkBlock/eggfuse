"""Replay consistency checks on archived source-alignment, redemption and fault counters."""
import argparse
import json
import sys
from pathlib import Path

from contract import ENDPOINTS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pair-source-frontier"))
from evidence import checked


def verify(folder):
    cases = checked(folder, ("results.json",), ("conjugate-gradient", "3mm"))
    for case, arms in cases.items():
        group, sealed = arms["group"], arms["sealed"]
        assert sealed["staging"] == group["staging"]
        staging = group["staging"]
        assert staging["slots_before_first_verify"] == staging["preconstructed"] == staging["granted"]
        assert staging["used"] == staging["payload_identity"] == staging["redeemed"] > 0
        assert staging["fresh"] == staging["used"] + staging["fallback"]
        for k in ENDPOINTS:
            assert sealed[k] == group[k] == arms["off"][k], (case, k)
        content = group["redemption"]
        identity = sealed["redemption"]
        assert content["attempts"] == content["content_reads"] == staging["used"]
        assert identity["attempts"] == identity["audit_comparisons"] == identity["fast_accepts"] == staging["used"]
        assert content["fast_accepts"] == identity["content_reads"] == identity["fast_denials"] == identity["missing_seals"] == 0

    faults = json.loads((folder / "faults.json").read_bytes())
    assert set(faults) == {"none", "reissued", "unsealed", "foreign", "stale", "withheld", "duplicate"}
    base = faults["none"]
    for kind, arm in faults.items():
        assert arm["aligned"] and all(arm["checks"].values())
        for k in ENDPOINTS:
            assert arm[k] == base[k], (kind, k)
        s, r = arm["staging"], arm["redemption"]
        assert r["content_reads"] == 0
        if kind in {"none", "duplicate"}:
            assert r["fast_accepts"] == base["staging"]["used"] == s["used"] > 0
            assert s["duplicate_denials"] == (s["used"] if kind == "duplicate" else 0)
        else:
            assert s["used"] == r["fast_accepts"] == 0
            assert s["fallback"] == s["fresh"] == base["staging"]["fresh"]
            failure = {"reissued": "foreign_denials", "unsealed": "foreign_denials", "foreign": "foreign_denials",
                       "stale": "stale_named", "withheld": "missing_named"}[kind]
            assert s[failure] > 0, kind
            if kind in {"reissued", "unsealed"}:
                denied = "reissued_denials" if kind == "reissued" else "missing_seals"
                assert r[denied] == r["audit_comparisons"] == r["fast_denials"] == r["attempts"] > 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path, nargs="?", default=HERE)
    verify(p.parse_args().folder)
    print("Verified both actual Pass 3 programs, source ledgers, immutable page identity and six fault arms.")
