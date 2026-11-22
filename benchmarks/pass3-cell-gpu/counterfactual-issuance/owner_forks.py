"""Intervene on two prospective owners from the same native issuance page."""
import argparse
from itertools import groupby
import json
from pathlib import Path
import random

from train import study, verify


def shared_result(seed):
    rng = random.Random(seed)
    def eq(i):
        return {"sort":"Expr", "eq":f"Value({i})"}
    def integer(i):
        return {"sort":"i64", "value":i}
    def row(table, *values):
        return dict(table=table,values=values,subsumed=False)
    # Two distinct keys, one actual e-class result. Both request Single(result).
    source_a, source_b, result, single = rng.sample(range(1000),4)
    rows = [row("Get",eq(source_a),integer(rng.randrange(4)),eq(result)),
            row("Get",eq(source_b),integer(rng.randrange(4)),eq(result))]
    if seed % 2:
        rows.append(row("Single",eq(result),eq(single)))
    rng.shuffle(rows)
    return rows


def collect(a):
    a.out.mkdir(parents=True,exist_ok=True)
    program,plans,req,spec=study["setup"](a,"dot-product")
    rows=[]
    missing=0
    corrupt_rejected=0
    with study["src"].base.session(a.native,program,plans) as run:
        for seed in range(41600,41600+a.cases):
            initial=shared_result(seed) if a.shared_result else study["generated"](seed)
            def episode(ids, corrupt=False):
                actor=dict(mode="pair",seed=seed,weights=[0.]*3,signed_pair=ids)
                config=study["matrix"]["cfg"](req,dict(spec,issuance_actor=actor,
                                          block_verifier=True,receipt_scan=2,reuse_returns=a.reuse_returns, wrong_port=corrupt),True)
                data=run(dict(config,generated_get_inputs=initial))
                if "source_error" in data and not corrupt:
                    raise ValueError(data["source_error"])
                return data
            base=episode(None)
            gold=run(dict(baseline=True,audit=True,generated_get_inputs=initial))
            for key in ("rhs","writes","resumes","state_sha","schedule","runs","events"):
                if base[key]!=gold[key]:
                    raise ValueError(("leaf vs exact",seed,key))
            actor=base["strict_named"]["issuance_actor"]
            pages=[list(group) for _,group in groupby(actor["pair_pages"],lambda r:r[:3])]
            pages=[p for p in pages if len(p)>=2]
            if not pages:
                missing+=1
                continue
            rng=random.Random(seed)
            page=pages[0] if a.shared_result else rng.choice(pages)
            if a.shared_result and len(page)!=2:
                raise ValueError("expected both initial Get parents together")
            left,right=rng.sample(page,2)
            if left[4]==right[4]:
                raise ValueError("owners cite same physical input")
            order=[left[3],right[3]]
            arms={}
            membership={}
            prefix=actor["pair_pages"].index(page[-1])+1
            for name,ids in (("none",None),("a",[order[0]]*2),("b",[order[1]]*2),("both",order)):
                d=base if ids is None else episode(ids)
                controls=d["strict_named"]["issuance_actor"]
                if controls["pair_pages"][:prefix]!=actor["pair_pages"][:prefix]:
                    raise ValueError("address prefix changed before departure")
                if [sid for sid,_,take in controls["decisions"] if take]!=sorted(set(ids or [])):
                    raise ValueError("different owner signed")
                verify(base,d)
                roots={r[2]:r[0] for r in d["root_recipe"]["commits"]}
                signed={roots[serial] for serial,owner,*_ in d["strict_named"]["signed_commits"]
                        if owner in (ids or [])}
                arms[name]=study["packets"](d)
                if arms["none"]-arms[name]!=len(signed):
                    raise ValueError("unattributed saving")
                membership[name]=signed
            if a.shared_result and membership["both"]:
                if a.reuse_returns and not (membership["a"] == membership["b"] == membership["both"]):
                    raise ValueError(("either signed root must preserve the productive successor",seed))
                if not a.reuse_returns and membership["a"] & membership["b"]:
                    raise ValueError(("fresh-only control registered the same birth twice",seed))
            if a.shared_result and a.reuse_returns and not corrupt_rejected and membership["a"] & membership["b"]:
                later=max(order)
                bad=episode([later,later],corrupt=True)
                if "strict named return port corruption" not in str(bad.get("source_error")):
                    raise ValueError(("wrong reused address was not rejected",seed))
                corrupt_rejected+=1
            rows.append(dict(seed=seed,addresses=[left,right],paid=arms,
                       common=len(membership["a"] & membership["b"]),
                       both_preserves_union=membership["both"]==membership["a"]|membership["b"]))
    summary=dict(corrupt_rejected=corrupt_rejected,reuse_returns=a.reuse_returns,shared_input_result=a.shared_result,episodes=a.cases, paired=len(rows),no_pair=missing,
                 a_cheaper=sum(r["paid"]["a"]<r["paid"]["b"] for r in rows),
                 b_cheaper=sum(r["paid"]["b"]<r["paid"]["a"] for r in rows),
                 tied=sum(r["paid"]["a"]==r["paid"]["b"] for r in rows),
                 shared_successor=sum(bool(r["common"]) for r in rows),
                 joint_differs=sum(not r["both_preserves_union"] for r in rows),
                 total_paid={k:sum(r["paid"][k] for r in rows) for k in ("none","a","b","both")})
    (a.out/"owner-forks.json").write_text(json.dumps(dict(summary=summary,episodes=rows),indent=2)+"\n")
    print(summary,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out"):
        p.add_argument(key,type=Path)
    p.add_argument("--cases",type=int,default=128)
    p.add_argument("--shared-result",action="store_true")
    p.add_argument("--reuse-returns",action="store_true")
    collect(p.parse_args())
