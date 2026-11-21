"""Select strict consumer schemas on realized child returns before opening the holdouts."""
import argparse
from collections import Counter
import json
from pathlib import Path
from native import strict,driver,summarize

# Do not break ties using held-out data or rule numbering.
DONORS=("dot-product","jacobi-1d")
OBJECTIVES=("commits","typed","typed_and_dynamic")


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    all_rows=Counter()
    donors={}
    for c in DONORS:
        prog,plan,req=strict.src.config(a,c)
        ids,_=strict.bake.base["schema_map"](prog)
        with strict.src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as get:
            gold=get({"audit":True})
        opt={"depth":1,"record_links":True,"partial":a.partial,"value_guards":a.guards}
        with strict.src.base.session(a.native,prog,plan) as get:
            v=get(dict(driver["filtered"](req,opt),audit=True,birth_ledger=True))
            row=summarize(v,gold,ids);del v
        donors[c]=row
        for key,x in row["outcome"].items():
            for k,value in x.items():all_rows[key,k]+=value
        print(c,row["removed"],row["typed"],row["dynamic"],len(row["outcome"]),flush=True)
    catalog=sorted({s for s,k in all_rows})
    ranks={}
    for obj in OBJECTIVES:
        def reward(s):
            if obj=="typed_and_dynamic":return all_rows[s,"typed"]+all_rows[s,"dynamic"]
            return all_rows[s,obj]
        ranks[obj]=[[key,reward(key)] for key in sorted(catalog,key=lambda s:(-reward(s),s)) if reward(key)>0]
    (a.out/"policy.json").write_text(json.dumps(dict(partial=a.partial,value_guards=a.guards,donors=donors,ranked=ranks),indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--partial",action="store_true")
    p.add_argument("--guards",action="store_true")
    run(p.parse_args())
