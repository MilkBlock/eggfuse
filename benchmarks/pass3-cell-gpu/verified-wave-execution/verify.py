"""Check all measured compositions against their five native Pass 3 executions."""
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent


def verify():
    checked=run_path(str(HERE.parent/"pair-source-frontier/evidence.py"))["checked"]
    data=checked(HERE,["small.json","large.json"],
                 ["sum-bits","dot-product","conjugate-gradient","3mm","deriche"],raw=False)
    for case,arms in data.items():
        off,filtered=arms["off"],arms["filter"]
        for mode in ("filter","packed","ports","pool"):
            v=arms[mode]
            for key in ("complete_scores","full_single","decisions","children","multi"):
                assert v[key]==off[key],(case,mode,key)
            assert v["verified"]+v["omitted"]==off["verified"]
            assert v["emitted"]+v["omitted"]==off["emitted"] and v["audited"]==v["omitted"]>0
            assert all(v[k]==filtered[k] for k in ("raw","wire_hash","wire_bytes","commits","physical"))
            if mode!="filter":
                assert 0<v["queue"]["verified"]<=v["queue"]["lanes"]==v["emitted"]
            if mode in ("ports","pool"):
                assert 0<v["transfers"][0]==v["transfers"][1]
        p,c=arms["pool"]["pool"],arms["pool"]["storage"]
        assert p["layout_bound"]==c["used"]==c["payload_identity"]==p["own"]+p["borrowed"]
        assert c["granted"]==c["used"]+c["unused"] and c["fresh"]==c["used"]+c["fallback"]
        assert c["offers_after_first_verify"]==c["slots_after_first_verify"]==0
    print("Verified the native integrated wave path, five source schedules, actual point reads and physically shared Cells.")


if __name__=="__main__":
    verify()
