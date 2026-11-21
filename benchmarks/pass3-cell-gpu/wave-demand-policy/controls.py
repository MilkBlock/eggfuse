"""Check denial controls and a source Run split over several proposal waves."""
import hashlib
import json
from pathlib import Path
from runpy import run_path
driver = run_path(str(Path(__file__).with_name("study.py")))
arguments, settings, source = (driver[k] for k in ("arguments", "settings", "source"))


def main():
    a = arguments()
    a.out.mkdir(parents=True, exist_ok=False)
    p, plan, req = source.common.config(a, "sum-bits")
    arms = settings(req, a)
    base = arms["coverage"]
    with source.base.session(a.exp / "compact-vanilla-20261121/vanilla-audit", p) as oracle:
        gold = oracle({"audit": True})
    results = {}
    with source.base.session(a.native, p, plan) as infer:
        for name in ("complete", "withheld", "foreign", "stale", "duplicate", "limited-wave", "zero-budget"):
            spec = base["spec_cells"].copy()
            if name in ("withheld","foreign","stale","duplicate"):
                spec["fault"] = name
            if name == "zero-budget":
                spec["cap"] = 0
            cfg = dict(base, spec_cells=spec, audit=True)
            if name == "limited-wave":
                cfg["proposal_wave"] = 32
            v = infer(cfg)
            q = source.base.summarize(v, gold)
            assert q["aligned"] and all(q["checks"].values())
            stats = v["spec_cells"]["counts"]
            evidence = {key:q[key] for key in ("rhs","commits","physical","root_ids","root_parents","nested_ids","children","state_sha")}
            digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
            results[name] = dict(source=digest, checks=q["checks"], counts=stats, demand=v["spec_cells"]["wave_demand"])
            if name in ("withheld", "foreign", "stale"):
                reason = {"withheld":"missing_named","foreign":"foreign_denials","stale":"stale_named"}[name]
                assert stats["used"] == 0 and stats[reason] > 0
            if name == "duplicate":
                assert stats["used"] == results["complete"]["counts"]["used"] == stats["duplicate_denials"] > 0
            if name == "limited-wave":
                assert stats["offers_after_first_verify"] > 0 and stats["slots_after_first_verify"] == 0
            if name == "zero-budget":
                assert stats["granted"] == stats["used"] == 0
            if name != "limited-wave":
                assert digest == results["complete"]["source"]
            print(name, stats["used"], stats["offers_after_first_verify"], flush=True)
    (a.out / "controls.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
