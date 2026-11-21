"""Check physical allocations, per-Run compatibility bounds and consuming-rule authority."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair-source-frontier"))
from evidence import checked


def verify():
    results=checked(HERE,("results.json",),("conjugate-gradient","3mm"))
    old=json.loads((HERE.parent/"sealed-lane-claims/results.json").read_bytes())
    equal=("preconstructed","granted","fresh","authorized_lanes","group_pages","offers","slabs","clipped",
           "header_capacity_bytes","private_payload_capacity_bytes","peak_private_bytes","bitmap_bytes","peak_bitmap_bytes")
    bounds=("rule_bound","layout_bound","run_bound","offered_layout_bound","offered_run_bound")
    for case,arms in results.items():
        a,b=arms["per-rule"],arms["shared"]
        assert a["run_layout_sha256"]==b["run_layout_sha256"]
        for key in equal:
            assert a["staging"][key]==b["staging"][key],key
        for key in bounds:
            assert a["pool"][key]==b["pool"][key]
        assert a["staging"]["used"]==old[case]["sealed"]["staging"]["used"]
        for row in (a,b):
            s,p,r=row["staging"],row["pool"],row["redemption"]
            assert p["rejected_layout"]==r["fast_denials"]==r["content_reads"]==0
            assert p["own"]+p["borrowed"]==r["fast_accepts"]==r["audit_comparisons"]==s["used"]==s["payload_identity"]
            assert s["used"]+s["unused"]==s["granted"]==s["slots_before_first_verify"] and s["offers_after_first_verify"]==0
            assert s["fallback"]+s["used"]==s["fresh"]
            assert p["rule_bound"]<=p["offered_layout_bound"]<=p["layout_bound"]<=p["run_bound"]
        assert a["pool"]["own"]==a["pool"]["rule_bound"] and a["pool"]["borrowed"]==0
        assert b["staging"]["used"]==b["pool"]["layout_bound"] and b["pool"]["borrowed"]>0
        assert 0<b["pool"]["switched_templates"]<=b["pool"]["borrowed"]
    f=json.loads((HERE/"faults.json").read_bytes())
    assert set(f)=={"per-rule","none","bad-layout","other-rule","reissued","stale","foreign","withheld","duplicate"}
    for kind,row in f.items():
        s,p=row["staging"],row["pool"]
        assert row["aligned"] and all(row["checks"].values())
        for key in ("rhs","raw","multi","commits","physical","root_parents","root_ids","nested_ids","cells","children","state_sha"):
            assert row[key]==f["none"][key]
        if kind=="none":assert s["used"]==p["layout_bound"]>p["rule_bound"]
        if kind=="bad-layout":
            assert p["rejected_layout"]>0 and p["borrowed"]==0 and s["used"]==p["rule_bound"]==f["per-rule"]["staging"]["used"]
        if kind=="duplicate":assert s["used"]==s["duplicate_denials"]==f["none"]["staging"]["used"]
        if kind in ("other-rule","foreign","reissued","stale","withheld"):
            key={"other-rule":"foreign_denials","foreign":"foreign_denials","reissued":"foreign_denials",
                 "stale":"stale_named","withheld":"missing_named"}[kind]
            assert s[key]>0 and s["used"]==0 and s["fresh"]==s["fallback"]
            if kind=="reissued":assert row["redemption"]["reissued_denials"]==s[key]


if __name__=="__main__":
    verify()
    print("Verified equal physical budgets, independent source ledgers, both layout ceilings and fault controls.")
