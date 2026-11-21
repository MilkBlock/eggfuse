"""Recompute all denominator definitions and native latency/physical crossing receipts."""
import json
from pathlib import Path
from statistics import median
from math import isclose
HERE=Path(__file__).resolve().parent
def read(p):
    return json.loads(p.read_bytes())


def check_matrix(matrix):
    birth=read(HERE.parent/"token-constructor-births/results.json")
    for c,g in matrix.items():
        base=g["arms"]["packed"]
        for arm,v in g["arms"].items():
            for key in ("rhs","commits","physical","root_parents","root_ids","nested_ids","children",
                        "state_sha","raw_parent_sha","recurrent","decisions","root_commit_sha","visible_sha",
                        "retired_sha","birth_sha","born","visible","rule_call_sha"):
                assert v[key]==base[key],(c,arm,key)
            assert all(v["checks"].values()) and median(v["ms"])==v["median_ms"]
            assert v["visible"]==birth[c]["retention"]["original_visible_per_committed_root"]["births"]
            n=sum(x["packets"] for x in v["categories"].values())
            assert sum(x["visible"] for x in v["categories"].values())==v["visible"]
            fam=v["family_counts"];cls=v["class_counts"];den=v["denominators"]
            assert n==den["forward"]
            assert den["bidirectional"]==n+cls["issued"]
            assert den["paid_groups"]==n+fam["absent"]+fam["stale"]
            full=(v["single_dispatches"]+cls["issued"]+v["single_residual_decisions"]+
                  v["categories"]["multi_literal"]["packets"]+fam["actions"]+fam["prototypes"]+v["child_candidates"])
            assert den["decisions_plus_return"]==full+cls["issued"]
            for key,units in den.items():
                assert isclose(v["per_packet"][key],v["visible"]/units)
            if arm in ("compound","reserved"):
                assert v["compound_work"]["admitted"]>0 and v["compound_work"]["receiver_computed"]>0
            if arm=="reserved":
                assert v["denominators"]==g["arms"]["compound"]["denominators"]
                assert v["staging"]["used"]==v["staging"]["payload_identity"]>0


def check_rss(name):
    data=read(HERE/name)
    calibration=read(HERE.parent/"verified-wave-rss/results.json")
    for c,g in data.items():
        absolute,increment=g["frozen_thresholds_kib"]
        assert [absolute,increment]==calibration[c]["thresholds_kib"]["0.9"]
        for samples in g["arms"].values():
            assert len(samples)==3
            for s in samples:
                points=s["trace"];start=points[0][1]
                assert s["peak_kib"]==max(b for _,b in points)
                for key,level in (("increment",start+increment),("absolute",absolute)):
                    t=next((t for t,b in points if b>=level),None)
                    assert s["crossings"][key]==["unreached" if t is None else "left" if start>=level else "reached",t]


if __name__=="__main__":
    for name in ("results.json","deriche.json","reserved.json"):check_matrix(read(HERE/name))
    for name in ("rss.json","reserved-rss.json"):check_rss(name)
    print("Verified combined FEPT, return traffic, prototype decisions, positive-node origins, pool redemption and fresh-process RSS.")
