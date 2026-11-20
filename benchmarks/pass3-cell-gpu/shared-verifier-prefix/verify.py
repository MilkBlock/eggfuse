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
    return data

if __name__=="__main__":
    print("Verified independent tickets, exact shared prefix receipts, live registers and full source/physical endpoints on",len(verify()),"programs.")
