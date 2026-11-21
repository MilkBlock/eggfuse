"""Verify default RipSat lowering, the four normal native executions and fixed RSS windows."""
import hashlib
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    meta = read(HERE / "manifest.json")
    receipts = read(HERE / "results.json")
    memory = read(HERE / "rss.json")
    original = read(HERE.parent / "token-constructor-births/results.json")
    calibration = read(HERE.parent / "verified-wave-rss/results.json")
    evidence = HERE.parent / "ripsat-donor-evidence"
    assert set(receipts) == set(memory) == {"sum-bits", "3mm"}
    assert meta["trace_library_sha256"] == sha(HERE.parent / "filtered-explicit-parent/library.json")
    for case, study in receipts.items():
        port_file = HERE.parent / "ripsat-strict-programs" / (case+".json")
        compiled = read(port_file)
        pin = meta["compiled"][case]
        assert sha(port_file) == pin["artifact_sha"]
        assert compiled["evidence_sha256"] == pin["evidence"] == sha(evidence / "evidence.json")
        assert compiled["trust_index_sha256"] == pin["trust"] == sha(evidence / "trust.json")
        assert compiled["target_sha256"] == pin["target"] == memory[case]["hashes"]["target_program"]
        assert memory[case]["hashes"]["native"] == meta["native_sha256"]
        assert memory[case]["hashes"]["semantic_results"] == sha(HERE / "results.json")
        paths = {tuple(map(tuple, path)) for path in compiled["strict_named"]["library"]}
        assert paths == {((143,1,55),)} and study["library"]["shared"] == 0
        arms = study["arms"]; leaf = arms["leaf"]
        ref = original[case]
        assert leaf["visible"] == ref["retention"]["original_visible_per_committed_root"]["births"]
        assert leaf["packets"] == ref["per_issued_root"]["denominator"] + ref["child_packets"]["selected"]
        assert leaf["internal"] == 0
        for name,v in arms.items():
            assert all(v["checks"].values()) and len(v["ms"]) == 4 and median(v["ms"]) == v["median_ms"]
            for key in ("rhs","runs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child"):
                assert v[key] == leaf[key], (case,name,key)
            assert sum(v["emitted"])+v["child"] == v["packets"]
            assert v["visible"]/v["packets"] == v["fept"]
            ordinals = set(v["covered_ordinals"])
            assert len(ordinals) == v["internal"] == sum(v["active_paths"].values()) == leaf["packets"]-v["packets"]
            if name != "leaf":
                prod=v["production"]
                assert prod.get("source_commits",0) == v["internal"] and prod.get("audit_score_inputs",0) == 0
            for path,example in v["examples"].items():
                assert example["named_parents"] and example["child_run"] > example["root_run"]
                assert json.loads(path) == example["applied_path"]
                for edge, address in zip(example["applied_path"],example["returned_ports"]):
                    assert edge[1] == address[1]
        t=set(arms["trace"]["covered_ordinals"]);r=set(arms["ripsat"]["covered_ordinals"])
        assert r and not t&r and t|r == set(arms["union"]["covered_ordinals"])
        assert set(tuple(map(tuple,json.loads(path))) for path in arms["ripsat"]["active_paths"]) == paths
        direct=arms["ripsat"]["path_nodes"]["[[143,1,55]]"]
        assert direct["typed"][0] == len(r) and direct["typed"][1] > 0
        assert direct["dynamic"] == direct["paid"] == [0,0]
    run_path(str(HERE/"rss.py"))["verify"](memory,receipts,calibration)
    entry=read(HERE/"entry-checks.json")
    assert entry["target_sha"]==meta["compiled"]["sum-bits"]["target"]
    assert len(entry["negative"])==4 and entry["strict_named"]=={"depth":1,"library":[[[143,1,55]]]}
    print("Verified final RipSat evidence, four partial-release programs, per-Run provenance, disjoint saved ordinals and RSS on two workloads.")


if __name__ == "__main__":
    verify()
