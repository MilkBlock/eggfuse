import json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
bake=run_path(str(HERE/"bake.py"))
ref=json.loads((HERE.parent/"joint-fept-actors/results.json").read_bytes())
bounds=json.loads((HERE/"bounds.json").read_bytes())
assert bounds==bake["run"]()
for c in (*bake["DONORS"],*bake["TEST"]):
    for w in (16,64):
        d=bake["samples"](c,w)
        assert all(d["checks"].values())
        assert all(x[1]==d["degrees"][x[0]]>=3 and 0<x[2]<=w and 0<=x[3]<=x[2] for x,y,n in d["windows"])
        assert sum(y*n for x,y,n in d["windows"])==d["captured"]<=d["residual_multi"]
        if c in ref:
            base=ref[c]["arms"]["both"]
            assert base["packets"]==d["packets"] and base["visible"]==d["visible"] and base["state_sha"]==d["state_sha"]
            assert sum(v.get("multi",0) for rid,v in base["rule_traffic"].items() if d["degrees"][int(rid)]>=3)==d["captured"]
            e=bounds[f"{c}/{w}"]["estimates"]
            assert e["oracle"]["saved"]>=max(e["donor"]["saved"],e["all"]["saved"])
print("Verified high-arity coverage, causal window counts, held-out return estimates and offline-only bounds.")
