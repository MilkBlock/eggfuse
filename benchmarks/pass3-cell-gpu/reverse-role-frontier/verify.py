"""Check complete issuance and source outcomes plus independent root-Q/child-K membership."""
import json
from pathlib import Path
import sys
from statistics import median

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"pair-source-frontier"))
from evidence import checked


def verify():
    cases=checked(HERE,("results.json",),("3mm","conjugate-gradient"))
    phases=json.loads((HERE/"phase.json").read_bytes())
    for case,arms in cases.items():
        ref=arms["off"];roots=ref["frontier"]["root_loop_positions"]
        for name in ("off","empty","gather","cached"):
            row=arms[name];s=row["frontier"];samples=phases[case][name]
            for key in ("raw","multi","commits","physical","root_parents","root_ids","nested_ids","wire_hash",
                        "wire_bytes","state_sha","source_wave","model_digest","children"):
                assert row[key]==ref[key],(case,name,key)
            assert len(samples)==3 and all(ms>0 and steps==s["root_loop_positions"] for ms,_,steps in samples)
            assert s["issuer_ms"]==s["frontier_ms"]==0
            if name in ("empty","gather","cached"):
                assert s["root_loop_positions"]<=roots
                if name=="empty" and s["empty_calls"]==0:
                    assert s["root_loop_positions"]==roots
            if name in ("gather","cached"):
                assert 0<=s["admissible"]<s["audit_decisions"]==s["root_candidates"]
                assert s["root_loop_positions"]<arms["empty"]["frontier"]["root_loop_positions"]
                assert s["later_roles"]<=s["routes"] and s["builds"]+s["hits"]==s["routes"]
                assert all(time>0 for _,time,_ in samples)
            if name=="cached":
                assert s["across_rules"]>0 and s["hits"]>0 and s["peak_bytes"]<=4<<20
                assert s["root_loop_positions"]==arms["gather"]["frontier"]["root_loop_positions"]
                assert s["key_probes"]<arms["gather"]["frontier"]["key_probes"]
            if name=="gather":assert s["hits"]==0


if __name__=="__main__":
    verify()
    print("Verified full raw issuance, source and physical ledgers, learned-signature frontier, and isolated issuer phase timings.")
