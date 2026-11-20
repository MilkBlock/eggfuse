"""Validate complete execution, proof sharing and the compiler-derived live register slice."""
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair-source-frontier"))
from evidence import checked

def verify(folder=HERE):
    data=checked(folder,["results.json"],["sum-bits","3mm"])
    for case, arms in data.items():
        assert set(arms)=={"vanilla","off","anchor","prefix","sibling","negative","live"}
        for arm,v in arms.items():
            if arm=="vanilla":continue
            assert len(v["ms"])==4 and v["decisions"]==arms["off"]["decisions"]
            s=v["family"]
            if arm=="off":
                assert s["accesses"]==s["families"]==0
                continue
            assert s["hits"]==s["audit_checks"]>0 and s["accesses"]==s["misses"]+s["hits"]
            assert s["families"]>0 and s["rules"]>=2*s["families"]
            assert s["sibling"]==sum(sum(p.values()) for p in s["audit_sibling_pairs"].values())
            if arm!="negative":assert s["sibling"]>0
            assert s["negative"]<=s["hits"] and s["sibling_negative"]<=s["sibling"]
            if arm=="anchor":assert s["step_hits"]==s["prefix_rules"]==0
            else:assert s["prefix_rules"]==5
            if arm in ("prefix","live"):assert s["step_hits"]>0
            if arm=="sibling":assert s["sibling"]==s["hits"]
            if arm=="negative":assert s["hits"]==s["negative"]
            if arm!="live":assert s["stored_slots"]==s["full_slots"]
        full=arms["prefix"]["family"];live=arms["live"]["family"]
        assert live["full_slots"]==full["full_slots"] and live["stored_slots"]<=full["stored_slots"]
        for key in ("accesses","misses","hits","sibling","negative","audit_sibling_pairs"):
            assert live[key]==full[key]
        assert live["stored_values"]<=full["stored_values"] and live["restored_values"]<=full["restored_values"]
    attr=checked(folder,["attributes.json"],["sum-bits","conjugate-gradient"])
    for case,arms in attr.items():
        assert set(arms)=={"vanilla","off","attr","different","joint"}
        for arm in ("attr","different","joint"):
            a=arms[arm]["attributes"]
            assert a["admitted_tables"]>0 and a["compiled_uses"]>a["admitted_tables"]
            assert a["calls"]>=a["hits"]==a["audit_checks"]>0
            assert sum(sum(row.values()) for row in a["pairs"].values())==a["hits"]
            assert 0<a["different_pivot_table"]<=a["different_rule"]<=a["hits"]
            assert a["hits"]==arms["off"]["single_work"][3]-arms[arm]["single_work"][3]
            if arm=="different":assert a["hits"]==a["different_rule"]
            assert arms[arm]["decisions"]==arms["off"]["decisions"]
        assert arms["attr"]["attributes"]["pairs"]==arms["joint"]["attributes"]["pairs"]
    import json
    phases=json.loads((folder/"phases.json").read_bytes())
    assert set(phases)==set(data)
    from statistics import median
    for arms in phases.values():
        assert set(arms)=={"off","prefix","live"}
        for v in arms.values():
            assert len(v["samples"])==3 and v["ms"]==list(map(median,zip(*v["samples"])))
    return data

if __name__=="__main__":
    print("Verified independent tickets, exact shared prefix receipts, live registers and full source/physical endpoints on",len(verify()),"programs.")
