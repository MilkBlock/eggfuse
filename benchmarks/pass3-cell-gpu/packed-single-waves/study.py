"""Compare row-wise tokens with page-shared singleton waves, with and without physical staging."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
group = run_path(str(HERE.parent / "group-named-cells/study.py"))
source = group["wave"].parent
KEYS = ("rhs","raw","multi","commits","physical","root_ids","root_parents","nested_ids","children","state_sha",
        "single_winners","multi_winners","wire_hash","decision","wave")


def settings(req, args):
    options = group["settings"](req, args)
    normal = options["off"]
    arms = {"off": normal, "packed": dict(normal, packed_single=True)}
    if args.staged:
        sealed = dict(options["group"], sealed_redemption=1)
        arms.update(group=sealed, packed_group=dict(sealed, packed_single=True))
    return arms


def observe(name, v, q, rows):
    single = v["single"]
    q["queue"] = single["packed"]
    q["widths"] = [single["ordinary_lane_bytes"], single["packed_lane_bytes"]]
    q["decision"] = single["adaptive_rows"]["decision_digest"]
    q["wave"] = v["multi"]["wave"]
    if name != "off":
        assert all(q[k] == rows["off"][k] for k in KEYS)
    if name.startswith("packed"):
        stats = q["queue"]
        assert stats["lanes"] == q["wave"]["sealed_single"] > 0
        assert 0 < stats["verified"] <= stats["lanes"] and stats["pages"] >= stats["banks"] > 0
        assert stats["pending_bytes"] == 0
        assert 0 < stats["peak_pending_bytes"] < rows["off"]["queue"]["peak_pending_bytes"]
        assert 0 < stats["total_queue_capacity_bytes"] < rows["off"]["queue"]["total_queue_capacity_bytes"]
    if name in ("group","packed_group"):
        c = q["storage"] = v["spec_cells"]["counts"]
        assert c["used"] == c["payload_identity"] == v["root_recipe"]["redemption"]["fast_accepts"] > 0
        if name == "packed_group":
            assert c == rows["group"]["storage"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("exp", "native", "out"):
        p.add_argument(name, type=Path)
    p.add_argument("--cases", nargs="+", default=["conjugate-gradient", "3mm"])
    p.add_argument("--staged", action="store_true")
    p.add_argument("--repeats", type=int, default=4)
    a = p.parse_args()
    a.seed = 1703
    a.cap = 8192
    a.policy = json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    source.study(a, settings, observe, None)
