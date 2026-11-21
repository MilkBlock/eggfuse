"""Fit/evaluate the macro choice with full coverage and distinct external/model/return counts."""
import argparse
from collections import Counter
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
single=run_path(str(HERE.parent/"causal-single-class/study.py"))
source=single["src"]
REFS=("raw","multi","physical","commits","rhs","root_parents","root_ids","nested_ids","children",
      "state_sha","decisions","source_final_serial","recurrent_final","cell_export_sha","coalescing_sha")
DONORS=("sum-bits","dot-product","jacobi-1d")


def collect(args):
    args.out.mkdir(parents=True,exist_ok=False)
    models={} if args.capture else json.loads(args.models.read_bytes())["models"]
    results={}
    for case in args.cases:
        p,plan,req=source.common.config(args,case)
        cfg=single["w"]["settings"](req,args)["packed"]
        with source.base.session(args.exp/"compact-vanilla-20261121/vanilla-audit",p) as ref:
            gold=ref({"audit":True})
        rows={}
        samples={}
        modes=["always"] if args.capture else ["never","always","previous","count",*models]
        if not args.capture and args.extra:
            assert all(k in modes for k in args.extra)
            modes=["never",*args.extra]
        with source.base.session(args.native,p,plan) as run:
            for name in modes:
                gate={"mode":"learned" if name in models else name,"capture":True}
                if name in models:gate["weights"]=models[name]
                s=dict(cfg,rows=dict(cfg["rows"],fept_gate=gate),class_actor=1)
                v=run(dict(s,audit=True,birth_ledger=True))
                assert "source_error" not in v,v.get("source_error")
                g=v["single"]["fept_gate"];calls=v["single"]["class_actor"]["rule_calls"]
                labels={(i[0],i[1]):i for i in calls}
                assert len(labels)==len(calls) and len(g["inputs"])==g["calls"]
                charged=saved=best=0
                decisions=[]
                for ep,rid,x,chose in g["inputs"]:
                    row=labels[(ep,rid)]
                    assert row[2] and bool(row[3])==chose and not row[-1]
                    emitted=row[6]
                    saved+=(emitted-1)*int(chose)
                    best+=max(emitted-1,0)
                    charged+=int(chose)
                    if args.capture:
                        decisions.append([ep,rid,x,emitted])
                assert charged==g["selected"]==v["single"]["class_actor"]["issued"]
                if args.capture:
                    sem=source.base.summarize(v,gold)
                    assert sem["aligned"] and all(sem["checks"].values())
                    ledger=v["constructor_births"]
                    visible_ids={f for f,_,hidden in ledger["endpoint"] if not hidden}
                    vis=sum(bool(e[3] and e[4] and e[7]&1 and e[0] in visible_ids) for e in ledger["rows"])
                    cls=v["single"]["class_actor"]
                    count=sum(v["root_recipe"]["emitted"])-cls["internal_receipts"]+cls["issued"]+v["merge_child"]["counts"][1]
                    q=dict(visible=vis,state_sha=v["state_sha"],fept=vis/count,packets=count)
                else:
                    q=single["result"](case,v,gold,True)
                q.update(choices=g["calls"],chosen=charged,saved=saved,oracle_saved=best)
                if args.capture:
                    # Attribute original surviving constructor identities to the rule
                    # call that actually committed their producer; the labels are
                    # computed only at the end of a completed training episode.
                    winners={r[2]:(r[5],r[3]) for r in v["root_recipe"]["commits"]}
                    by_call=Counter(winners[e[4]] for e in ledger["rows"] if e[3] and e[4] and e[7]&1 and e[0] in visible_ids)
                    assert sum(by_call.values())==vis
                    for record in decisions:
                        record.append(by_call[tuple(record[:2])])
                    (args.out/f"{case}.json").write_text(json.dumps(dict(case=case,samples=decisions,
                         inputs="pre-issuance; prior observations only",visible=q["visible"],source=q["state_sha"]),
                         separators=(",",":"))+"\n")
                elif rows:
                    base=rows["never"]
                    assert all(q[k]==base[k] for k in REFS),(case,name)
                    assert q["packets"]==base["packets"]-saved
                    assert q["visible"]==base["visible"] and q["oracle_saved"]==base["oracle_saved"]
                q.pop("ms",None);q.pop("wall_ms",None)
                q["fept_charging_gate_declines"]=q["visible"]/(q["packets"]+g["calls"]-charged)
                rows[name]=q
                gate["capture"]=False
                samples[name]=s
                del v
                print(case,name,q["chosen"],q["packets"],round(q["fept"],5),flush=True)
            if not args.capture and args.repeats:
                # Timing is secondary. Charge inference costs to actual deployed choices,
                # keeping diagnostic and training tapes out of the measured sessions.
                timed=[x for x in ["never","always","count","reward-0","reinforce-8"] if x in rows]
                for rep in range(args.repeats+1):
                    for name in timed[rep%len(timed):]+timed[:rep%len(timed)]:
                        v=run(dict(samples[name],audit=False))
                        assert v["state_sha"]==rows[name]["state_sha"] and v["single"]["fept_gate"]["selected"]==rows[name]["chosen"]
                        if rep:rows[name].setdefault("ms",[]).append(v["ms"])
                for name in timed:rows[name]["median_ms"]=median(rows[name]["ms"])
        results[case]=rows
        (args.out/"results.json").write_text(json.dumps(results,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--capture",action="store_true")
    p.add_argument("--models",type=Path,default=HERE/"models.json")
    p.add_argument("--cases",nargs="+",default=["conjugate-gradient","3mm"])
    p.add_argument("--extra",nargs="+",default=[])
    p.add_argument("--repeats",type=int,default=3)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    collect(a)
