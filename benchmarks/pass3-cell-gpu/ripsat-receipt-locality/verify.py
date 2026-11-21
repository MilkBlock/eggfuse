"""Check semantic identity, all work ledgers and version-index and request invariants offline."""
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent

def read(name):
    return json.loads((HERE/name).read_bytes())

SEMANTICS=("rhs","runs","state_sha","parents","roots","nested","cells","commits","physical","children","score","births_sha","end_sha",
           "single_winners","multi_winners","new","visible","child_candidates","child","emitted","internal","set_internal",
           "signed_ordinals_sha","terminal_ordinals_sha","set_origins","packets")

def verify():
    for case,g in read("results.json").items():
        arms=g["arms"];base=arms["all"]
        for mode,q in arms.items():
            assert all(q[k]==base[k] for k in SEMANTICS) and all(q["checks"].values())
            w=q["scan"]
            assert q["fept"]==q["visible"]/q["packets"] and q["median_ms"]==median(q["ms"])
            assert len(q["ms"])==5 and len(q["profile"])==3 and w["row_reads"]<=w["member_checks"]
            assert all(s["receiver_ns"]>0 and s["row_reads"]==w["row_reads"] for s in q["profile"])
            assert not w["profile"] and w["receiver_ns"]==0
        x,y,z=(arms[n]["scan"] for n in ("all","early","indexed"))
        assert x["possible"]==y["possible"]==z["possible"]==x["visited"]==y["visited"]
        assert z["visited"]+z["excluded_by_version"]==z["possible"] and z["excluded_by_version"]==y["excluded_by_version"]>0
        assert x["row_reads"]>y["row_reads"]==z["row_reads"]
        assert z["stamped"]>0 and x["stamped"]==y["stamped"]==0
        assert g["faults"]["missing"]["emitted"]==g["faults"]["stale"]["emitted"] and g["faults"]["wrong_fields"]["message"]
    for case,arms in read("joint.json").items():
        base=arms["direct"]
        for name,q in arms.items():
            assert all(q[k]==base[k] for k in SEMANTICS) and all(q["checks"].values())
            assert len(q["ms"])==4 and len(q["profiles"])==3 and median(q["ms"])==q["median_ms"]
            if name.startswith("higher"):
                s=q["owners"]
                assert s["transferred"]==s["stable_address"] and s["terminal_commits"]==q["set_internal"]>0
                assert s["queued_requests"]==s["requests"]==s["replies"]==s["transferred"]+s["retired_no_result"]+s["retired_stale"]
        assert arms["higher-index"]["owners"]["transferred"]==arms["higher"]["owners"]["transferred"]
        assert arms["higher-index"]["scan"]["row_reads"]==arms["direct-index"]["scan"]["row_reads"]<base["scan"]["row_reads"]
    historic=read("../verified-wave-rss/results.json")
    for case,g in read("rss.json").items():
        assert g["levels_kib"]==historic[case]["thresholds_kib"]["0.9"]
        for arm,runs in g["arms"].items():
            assert len(runs)==3
            expected=read("joint.json")[case][arm]
            for r in runs:
                assert r["endpoints"]["source"]==expected["state_sha"]
                assert r["endpoints"]["emitted"]==expected["emitted"] and r["endpoints"]["internal"]==expected["internal"]
                points=r["trace"];absolute,increment=g["levels_kib"]
                assert r["peak_kib"]==max(b for _,b in points)
                for key,level in (("absolute",absolute),("increment",points[0][1]+increment)):
                    first=next((t for t,b in points if b>=level),None)
                    measured,_gap=r["crossings"][key]
                    assert measured==["unreached" if first is None else "left" if points[0][1]>=level else "reached",first]
    print("Verified direct and specialized owners, exact ordered results, physical objects, version pruning and charged timing samples.")

if __name__=="__main__":
    verify()
