"""Check native full-pass endpoints, matched proposals and grants derived from sealed offer counts."""
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
checked = run_path(str(HERE.parent/"pair-source-frontier/evidence.py"))["checked"]


def load(name):
    return json.loads((HERE/name).read_bytes())


def verify():
    for name, cases in (("results.json",("conjugate-gradient","3mm")), ("transfer.json",("deriche",)),
                        ("seed1709.json",("sum-bits","dot-product","conjugate-gradient"))):
        for case, arms in checked(HERE, [name], cases).items():
            for mode, v in arms.items():
                if mode in ("off","vanilla"):
                    continue
                assert v["score"] == arms["off"]["score"]
                d, c = v["demand"], v["staging"]
                assert v["seal"]["fast_accepts"] == c["payload_identity"] == c["used"]
                assert c["used"] + c["unused"] == c["granted"]
                assert c["used"] + c["fallback"] == v["root_allocated"]
                assert c["offers_after_first_verify"] == c["slots_after_first_verify"] == 0
                if mode != "entry":
                    assert d["batches"] > 0 and d["post_issue_grants"] == c["granted"]
                    if mode != "delay":
                        assert d["excess_at_issue"] == 0
                    if mode not in ("delay", "clip"):
                        assert d["predictions"] == d["nonempty_rules"] > 0
    for name in ("curves.json","tight.json"):
        for case, arms in load(name).items():
            for mode, v in arms.items():
                assert v["source"] == arms["entry"]["source"]
                assert all(0 <= hits <= min(fresh, granted) and fresh<=offers
                           for _, offers, fresh, granted, hits in v["curve"])
                assert v["totals"] == [sum(r[k] for r in v["curve"]) for k in range(1, 5)]
                if name == "curves.json" and case == "3mm":
                    c = load("results.json")[case][mode]["staging"]
                    assert v["totals"] == [c["offers"], c["fresh"], c["granted"], c["used"]]
                if name == "tight.json":
                    assert max(r[3] for r in v["curve"])<=64
    f = load("controls.json")
    for name, v in f.items():
        assert all(v["checks"].values())
        if name != "limited-wave":
            assert v["source"] == f["complete"]["source"]
    assert f["limited-wave"]["counts"]["offers_after_first_verify"] > 0
    assert f["limited-wave"]["counts"]["slots_after_first_verify"] == 0
    for name in ("withheld", "foreign", "stale", "zero-budget"):
        assert f[name]["counts"]["used"] == 0
    assert f["duplicate"]["counts"]["duplicate_denials"] == f["complete"]["counts"]["used"] > 0
    print("Verified native wave forecasts, per-Run capacity curves, partial waves, terminal graphs and fault denials.")


if __name__ == "__main__":
    verify()
