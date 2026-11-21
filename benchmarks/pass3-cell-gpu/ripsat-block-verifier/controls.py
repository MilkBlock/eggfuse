"""Measure receiver probes and time to calibrated RSS in fresh processes."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
common = run_path(str(HERE / "study.py"))
study = common["study"]
rss = run_path(str(HERE.parent / "ripsat-publication-matrix/rss.py"))


def measure(a, case):
    program, plans, req, plan = study["setup"](a, case)
    level = json.loads(rss["cal_file"].read_bytes())[case]["thresholds_kib"]["0.9"][1]
    arms = {}
    with study["src"].base.session(a.native, program, plans) as run:
        for name, block in (("generic", False), ("block", True)):
            spec = dict(plan, block_verifier=block, receipt_scan=2,
                        issuance_actor=dict(mode="greedy", seed=0, weights=common["weights"]))
            cfg = study["matrix"]["cfg"](req, spec)
            v = run(cfg)
            root = v["root_recipe"]
            sig = v["strict_named"]
            endpoints = dict(runs=v["runs"], state_sha=v["state_sha"], emitted=root["emitted"],
                             internal=sig["counts"]["source_commits"], set_internal=sig["set_publication"]["confirmed"])
            arms[name] = dict(config=cfg, endpoints=endpoints, header_checks=root["root_header_checks"],
                              rejected=root["rejected"], trials=[], single_verify_ns=[])
        for lap in range(5):
            for name in (list(arms) if lap % 2 else reversed(arms)):
                arm = arms[name]
                cfg = arm["config"]
                v = run(dict(cfg, rows=dict(cfg["rows"], profile=True)))
                assert v["state_sha"] == arm["endpoints"]["state_sha"]
                if lap:
                    ns = v["single"]["adaptive_rows"]["phase_ns"][3]
                    assert ns > 0
                    arm["single_verify_ns"].append(ns)
        leaf = dict(spec, issuance_actor=dict(spec["issuance_actor"], mode="leaf"))
        leaf_result = run(study["matrix"]["cfg"](req, leaf))
        assert leaf_result["state_sha"] == endpoints["state_sha"]
        assert all(leaf_result["strict_named"]["set_publication"][k] == 0 for k in
                   ("admissions", "direct_binds", "completed_blocks"))
    assert arms["generic"]["endpoints"] == arms["block"]["endpoints"]
    assert arms["generic"]["header_checks"] > arms["block"]["header_checks"]
    for i in range(4):
        for j, name in enumerate(list(arms) if i % 2 else reversed(arms)):
            arm = arms[name]
            pair = {sample:rss["one"](a.native, program, plans, arm["config"], sample, arm["endpoints"])
                    for sample in ((True, False) if (i+j)%2 else (False, True))}
            trace = pair[True]["trace"]
            arm["trials"].append(dict(growth_crossing=rss["crossing"](trace, trace[0][1] + level),
                                      peak_kib=max(x[1] for x in trace), plain_ms=pair[False]["ms"]))
    for arm in arms.values():
        del arm["config"]
    return dict(growth_kib=level, arms=arms)


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
