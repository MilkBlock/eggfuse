"""Compare the same frozen policy with generic and block receivers on full source runs."""
import argparse
import cProfile
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
issuer = HERE.parent / "ripsat-issuance-rl"
study = run_path(str(issuer / "study.py"))
weights = json.loads((issuer / "actor.json").read_text())["weights"]


def measure(a, case):
    program, plans, req, plan = study["setup"](a, case)
    def config(block, audit=False, **extra):
        spec = dict(plan, issuance_actor=dict(mode="greedy", seed=0, weights=weights),
                    block_verifier=block, receipt_scan=2, **extra)
        return study["matrix"]["cfg"](req, spec, audit)
    with study["src"].base.session(a.exp / "compact-vanilla-20261121/vanilla-audit", program) as oracle:
        gold = oracle({"audit": True})
    rows = {}
    with study["src"].base.session(a.native, program, plans) as run:
        previous = None
        for name, block in (("generic", False), ("block", True)):
            v = run(config(block, True))
            summary, _ = study["matrix"]["summarize"](v, gold, True)
            sig = v["strict_named"]
            counts = sig["set_publication"]
            assert counts["completed_blocks"] == (counts["confirmed"] if block else 0)
            if block:
                assert 0 < counts["exhausted_fresh_ports"] <= counts["completed_blocks"]
            assert counts["confirmed"] > 0
            assert counts["direct_binds"] == (len(sig["signed_commits"]) if block else 0)
            assert counts["capture_row_reads"] == (0 if block else counts["fresh_activations"])
            assert counts["replayed_operands"] == counts["capture_row_reads"]
            if previous:
                for key in ("rhs", "writes", "resumes", "runs", "state_sha", "schedule", "events"):
                    assert previous[key] == v[key], key
                for key in ("signed_commits", "set_commits"):
                    assert previous["strict_named"][key] == sig[key], key
                assert previous["root_recipe"]["commits"] == v["root_recipe"]["commits"]
            rows[name] = dict(counts=counts, packets=summary["packets"], checks=summary["checks"],
                              fept=summary["fept"], ms=[], bind_ns=[], capture_ns=[], receiver_ns=[])
            previous = v
        for fault in ("stale", "missing"):
            v = run(config(True, True, set_fault=fault))
            for key in ("rhs", "writes", "resumes", "runs", "state_sha", "schedule"):
                assert previous[key] == v[key], (fault, key)
            assert v["strict_named"]["set_publication"]["confirmed"] == 0
            assert study["packets"](v) - rows["block"]["packets"] == counts["confirmed"]
        broken = run(config(True, True, set_fault="wrong_fields"))
        assert "Set activation key/value or version differs" in broken.get("source_error", "")
        for lap in range(7):
            arms = list(rows) if lap % 2 else list(reversed(rows))
            for name in arms:
                block = name == "block"
                for profile in (False, True):
                    v = run(config(block, receipt_profile=profile))
                    assert v["state_sha"] == previous["state_sha"] and v["runs"] == previous["runs"]
                    if not lap:
                        continue
                    if profile:
                        sig = v["strict_named"]
                        for dest, ns in (("bind_ns", sig["set_publication"]["internal_bind_ns"]),
                                         ("capture_ns", sig["set_publication"]["capture_ns"]),
                                         ("receiver_ns", sig["receipt_scan"]["receiver_ns"])):
                            rows[name][dest].append(ns)
                    else:
                        rows[name]["ms"].append(v["ms"])
    for row in rows.values():
        row["median"] = {k:median(row[k]) for k in ("ms", "bind_ns", "capture_ns", "receiver_ns")}
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("exp", "native", "output"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    a.out = a.output.parent
    data = {}
    for case in ("sum-bits", "3mm"):
        data[case] = measure(a, case)
        a.output.write_text(json.dumps(data, indent=2) + "\n")
        print(case, {k:v["median"] for k,v in data[case].items()}, flush=True)
