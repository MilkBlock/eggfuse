"""Check matching physical budgets, native source proofs, and fixed-class ceiling offline."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def data(name):
    return json.loads((HERE/name).read_bytes())


def verify():
    evidence = data("manifest.json")
    for f,h in evidence["files"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==h, f
    results=data("results.json")
    assert set(results)=={"conjugate-gradient","3mm"}
    keys=("rhs","raw","multi","wire_hash","root_ids","nested_ids","root_parents","commits","children",
          "physical","state_sha","score","single_winners","multi_winners","cells")
    for case,arms in results.items():
        assert set(arms)=={"vanilla","off","original","offers","clip","fraction","coverage"}
        entry=arms["off"]
        for name,q in arms.items():
            if name=="vanilla":continue
            assert q["aligned"] and all(q["checks"].values()) and all(q[k]==entry[k] for k in keys)
            assert len(q["ms"])==4 and q["rhs"]==q["neural_rhs"]
            route=q["route"]; stage=q["staging"]
            for k in ("runs","grants","source_budget_sha","offers_bound","class_oracle"):
                assert route[k]==entry["route"][k],(case,name,k)
            assert stage["granted"]==stage["preconstructed"]==sum(route["grants"])
            for k in ("used","payload_identity","redeemed"):
                assert stage[k]==q["seal"]["fast_accepts"]==q["seal"]["audit_comparisons"]==route["actual"]
            for k in ("header_capacity_bytes","private_payload_capacity_bytes","peak_private_bytes","slabs"):
                assert stage[k]==entry["staging"][k]
            assert route["actual"]<=route["class_oracle"]<=route["offers_bound"]<=stage["granted"]
            assert stage["used"]+stage["unused"]==stage["granted"]
            if name not in ("off","original"):assert route["moved"]>0
            if name!="off":assert route["quiet_runs"]==arms["original"]["route"]["quiet_runs"]>0
        assert entry["staging"]["used"]==arms["original"]["staging"]["used"]
    faults=data("faults.json")
    assert set(faults)=={"none","stale","foreign","duplicate","reissued","unsealed","withheld"}
    for name,q in faults.items():
        assert q["aligned"] and all(q["checks"].values())
        assert all(q[k]==faults["none"][k] for k in keys if k!="score")
        c=q["staging"];seal=q["seal"]
        assert q["route"]["source_budget_sha"]==faults["none"]["route"]["source_budget_sha"]
        if name in ("foreign","reissued","unsealed"):
            assert c["used"]==0 and seal["fast_denials"]>0
        if name in ("stale","withheld"):
            assert c["used"]==0 and c[{"stale":"stale_named","withheld":"missing_named"}[name]]>0
        if name=="duplicate":
            assert c["duplicate_denials"]==c["used"]==faults["none"]["staging"]["used"]>0
    print("Both fixed-budget native audits, six physical routes, and seven receipt controls agree.")


if __name__=="__main__":
    verify()
