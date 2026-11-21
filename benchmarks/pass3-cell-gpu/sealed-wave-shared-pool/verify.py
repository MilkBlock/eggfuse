"""Verify physical capacity and authorization equalities under each frozen forecast."""
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair-source-frontier"))
from evidence import checked

CAPACITY=("requested","clipped","granted","preconstructed","fresh","offers","slabs","peak_slots",
          "header_capacity_bytes","private_payload_capacity_bytes","peak_private_bytes","group_pages","authorized_lanes",
          "peak_bitmap_bytes","bitmap_bytes","slots_before_first_verify","offers_before_first_verify")
BOUNDS=("rule_bound","run_bound","layout_bound","offered_layout_bound","offered_run_bound")
MODES=("entry","clip","coverage","fraction")


def verify():
    data=checked(HERE,("results.json",),("conjugate-gradient","3mm"))
    paired=json.loads((HERE/"paired.json").read_bytes())
    earlier=json.loads((HERE.parent/"cross-rule-cell-pool/results.json").read_bytes())
    for case,arms in data.items():
        for name in MODES:
            row=arms[name];other=paired[case][name]
            assert all(other["checks"].values())
            for key, expected in other["ledgers"].items():
                assert row[key]==expected
            c,p,s=row["staging"],row["pool"],row["seal"]
            assert all(c[k]==other["staging"][k] for k in CAPACITY)
            assert row["run_layout_sha256"]==other["run_layout_sha256"]
            assert all(p[b]==other["pool"][b] for b in BOUNDS)
            assert c["used"]==s["fast_accepts"]==s["audit_comparisons"]==c["payload_identity"]==p["layout_bound"]
            assert p["own"]+p["borrowed"]==p["layout_bound"]>=p["rule_bound"]==other["staging"]["used"]
            assert s["content_reads"]==s["fast_denials"]==p["rejected_layout"]==0
            assert c["used"]+c["unused"]==c["slots_before_first_verify"]==c["granted"]
            assert c["used"]+c["fallback"]==c["fresh"] and c["offers_after_first_verify"]==0
            if name!="entry":
                assert p["from_inactive_donors"]==0 and p["offered_layout_bound"]==p["layout_bound"]
                assert row["demand"]["post_issue_grants"]==c["granted"] and row["demand"]["excess_at_issue"]==0
                if name!="clip":assert 0<row["demand"]["predictions"]==row["demand"]["nonempty_rules"]
            else:
                assert p==earlier[case]["shared"]["pool"]
    faults=paired["sum-bits"]
    assert set(faults)=={"none","layout","other-rule","reissued","stale","duplicate"}
    for kind,r in faults.items():
        assert all(r["checks"].values()) and r["ledgers"]==faults["none"]["ledgers"]
        s,p=r["counts"],r["pool"]
        if kind=="layout":
            assert p["rejected_layout"]>0 and p["borrowed"]==0 and s["used"]==p["rule_bound"]
        if kind=="duplicate":
            assert s["duplicate_denials"]==s["used"]==faults["none"]["counts"]["used"]>0
        if kind in ("other-rule","reissued","stale"):
            assert s["used"]==0 and s["fallback"]==s["fresh"]
            assert s["stale_named" if kind=="stale" else "foreign_denials"]>0
            if kind=="reissued":assert r["seal"]["reissued_denials"]>0


if __name__=="__main__":
    verify()
    print("Verified four frozen forecasts, matched physical budgets within every policy, source semantics, native capacity bounds and fault controls.")
