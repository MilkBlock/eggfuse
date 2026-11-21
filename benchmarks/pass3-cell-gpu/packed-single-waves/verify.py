"""Independently check native semantics, compact queue capacity, denied private claims and RSS."""
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent


def verify():
    checked = run_path(str(HERE.parent/"pair-source-frontier/evidence.py"))["checked"]
    graph = checked(HERE,["results.json","transfer.json"],["conjugate-gradient","3mm","deriche","sum-bits","dot-product"])
    rss = json.loads((HERE/"rss.json").read_bytes())
    for case, arms in graph.items():
        for name in ("packed","packed_group"):
            if name not in arms:
                continue
            ref=arms["off" if name=="packed" else "group"]
            row=arms[name]
            assert row["decision"] == ref["decision"] and row["wire_hash"] == ref["wire_hash"]
            assert row["widths"] == ref["widths"] and row["widths"][0]>row["widths"][1]>0
            p,q = row["queue"],ref["queue"]
            assert 0 < p["verified"] <= p["lanes"] == ref["wave"]["sealed_single"]
            assert p["pending_bytes"] == q["pending_bytes"] == 0
            for metric in ("peak_pending_bytes","total_queue_capacity_bytes"):
                assert 0<p[metric]<q[metric]
            if name=="packed_group":
                assert ref["storage"]==row["storage"]
    for case,v in rss.items():
        assert set(v)==set(graph[case])-{"vanilla"}
        for k,r in v.items():
            assert len(r["bytes"])==3 and r["median"]==median(r["bytes"])
    controls=json.loads((HERE/"controls.json").read_bytes())
    assert all(v["digest"]==controls["none"]["digest"] for v in controls.values())
    assert controls["duplicate"]["duplicates"]==controls["none"]["used"]>0
    assert all(controls[k]["used"]==0 for k in ("withheld","stale","foreign"))
    print("Verified compact and expanded waves on five native programs, source and physical provenance, faults and RSS.")


if __name__=="__main__":
    verify()
