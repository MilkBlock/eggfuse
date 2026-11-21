import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/"results.json").read_bytes())
for case,run in data.items():
    arms=run["arms"];leaf=arms["leaf"]
    for mode,q in arms.items():
        assert all(q["checks"].values())
        for k in ("rhs","runs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child"):
            assert q[k]==leaf[k]
        assert q["fept"]==q["visible"]/q["packets"] and leaf["packets"]-q["packets"]==q["internal"]
        assert sum(v["commits"] for v in q["rules"].values())==q["internal"]
        if mode in ("guarded","two"):
            seen,rejected,accepted=q["guard_counts"]
            assert min(rejected,accepted)>0 and rejected+accepted==seen
    assert run["corruption_rejected_at_run"]<leaf["runs"]
print("Verified actual guarded named releases, per-consumer constructor origins and negative control.")
