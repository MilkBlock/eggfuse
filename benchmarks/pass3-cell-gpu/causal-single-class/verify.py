"""Check physical denominators, recurrent state and complete native execution for the class actor."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def data(name):return json.loads((HERE/name).read_bytes())

def verify():
    for f,h in data("manifest.json")["files"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==h,f
    results=data("results.json")
    assert set(results)=={"sum-bits","conjugate-gradient","3mm"}
    exact=("rhs","raw","multi","wire_hash","commits","physical","source_pass_rhs","root_ids","root_parents",
           "nested_ids","children","state_sha","single_winners","multi_winners","cells","direct_cells","root_allocated",
           "decisions","recurrent_final","source_final_serial","queue","verifier_activity","original_issued_single",
           "original_issued_multi","selected_children","cell_export_sha","coalescing_sha","public_call_sha","logged_calls",
           "born","visible")
    for case,result in results.items():
        b=result["arms"]["packed"];v=result["arms"]["class"]
        assert all(b[k]==v[k] for k in exact)
        assert b["actor"]["recurrence_digest"]==v["actor"]["recurrence_digest"]
        c=v["actor"];assert c["issued"]==sum(c["masks"])>0
        assert c["internal_receipts"]+c["residual_receipts"]==v["original_issued_single"]
        assert c["accepted_by_action"]==c["internal_receipts"]+c["scalar_rejected"]<=c["eligible_after_prefilters"]
        assert c["logit_evaluations"]==2*c["issued"] and c["empty"]<=c["issued"]
        for row in (b,v):
            g=row["groups"];assert all(row["checks"].values())
            assert row["packets"]==sum(k["packets"] for k in g.values())
            assert g["child"]["packets"]==row["selected_children"] and g["multi"]["packets"]==row["original_issued_multi"]
            assert sum(k["visible"] for k in g.values())==row["visible"]
            assert row["fept"]==row["visible"]/row["packets"]
            assert row["fept_including_feedback"]==row["visible"]/(row["packets"]+g["class"]["packets"])
            assert all(k["zero"]+k["one"]+k["two_plus"]==k["packets"] for k in g.values())
            wire=row["canonical_wire"]
            assert wire["descriptors"]==64*row["actor"]["issued"] and wire["feedback"]==20*row["actor"]["issued"]
            assert wire["both"]==sum(wire[i] for i in ("single_literals","unchanged_multi","unchanged_selected_child","descriptors","feedback"))
            assert len(row["ms"])==len(row["wall_ms"])==4
        assert b["packets"]-v["packets"]==c["internal_receipts"]-c["issued"]>0
        assert set(result["faults"])=={"2","3","4"}
    print("Three complete native endpoint, origin, recurrent, receipt, packet-budget and corruption audits passed.")
if __name__=="__main__":verify()
