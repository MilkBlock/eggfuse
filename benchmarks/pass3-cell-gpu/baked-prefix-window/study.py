"""Capture causal window features and the exact number of deployed descendant packets."""
import argparse,json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE.parent/'joint-fept-actors/study.py'))
source=driver["src"]


def row(case,program,plans,req,gold,a,width):
    cfg=driver["settings"](req,a,True)["both"]
    with source.base.session(a.native,program,plans) as infer:
        v=infer(dict(cfg,audit=True,prefix_window_survey=width,birth_ledger=True))
    assert "source_error" not in v,v.get("source_error")
    q=source.base.summarize(v,gold)
    assert q["aligned"] and all(q["checks"].values())
    tally=v["multi"]["windows"]
    assert tally["width"]==width
    logical={e[0] for e in v["constructor_births"]["rows"] if e[7]&1 and e[3] and e[4]}
    visible={k for k,_,hidden in v["constructor_births"]["endpoint"] if not hidden}
    multi=v["multi"];action=v["single"]["class_actor"];pair=multi["pair_actor"]
    child=v["merge_child"]["counts"][1]
    # The independent per-rule source counters include only literal pages after the pair actor.
    plans_data=json.loads(plans.read_bytes())
    from_rows=sum(n*freq for _,n,freq in tally["hist"])
    residual=multi["counts"]["raw_tuples"]-pair["declared_lanes"]
    total=root_count(v,action,pair,child)
    return dict(visible=len(logical&visible),physical=q["physical"],rhs=q["rhs"],state_sha=q["state_sha"],
                checks=q["checks"],packets=total,expanded_multi=multi["counts"]["raw_tuples"],residual_multi=residual,
                degrees=[len(p["linked"]) if p else 0 for p in plans_data],captured=from_rows,windows=tally["hist"])


def root_count(v,action,pair,child):
    s,m=v["root_recipe"]["emitted"]
    assert m==pair["external_residual"]
    return s+m+child-action["internal_receipts"]+action["issued"]+pair["groups"]


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["dot-product","jacobi-1d","conjugate-gradient","3mm"])
    p.add_argument("--widths",nargs="+",type=int,default=[16,64])
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())["models"]["fraction"]
    for case in a.cases:
        prog,plans,req=source.common.config(a,case)
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as exact: gold=exact({"audit":True})
        for w in a.widths:
            stats=row(case,prog,plans,req,gold,a,w)
            (a.out/(case+f'-{w}.json')).write_text(json.dumps(stats,separators=(',',':'))+'\n')
            print(case,w,stats["captured"],len(stats["windows"]),flush=True)
