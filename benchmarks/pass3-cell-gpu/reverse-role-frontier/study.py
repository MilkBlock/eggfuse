"""Measure root semijoins of independently generated parents on fully aligned CPU Pass 3."""
from argparse import ArgumentParser
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
verified=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
source=verified["source"]
MODES={"off":0,"empty":1,"gather":2,"cached":3}
KEYS=("rhs","commits","raw","multi","wire_hash","wire_bytes","physical","root_parents",
      "root_ids","nested_ids","children","cells","state_sha","single_winners","multi_winners")


def settings(req,a):
    packed=verified["settings"](req,a)["packed"]
    return {name:dict(packed,role_frontier=n) for name,n in MODES.items()}


def observe(arm,v,q,rows):
    q["frontier"]=v["multi"]["role_frontier"]
    q["model_digest"]=v["single"]["adaptive_rows"]["decision_digest"]
    q["source_wave"]=v["multi"]["wave"]
    q["visits"]=v["multi"]["counts"]["approximate_visits"]
    if arm!="off":
        for k in (*KEYS,"model_digest","source_wave"):
            assert q[k]==rows["off"][k],(arm,k)
    if arm in ("gather","cached"):
        s=q["frontier"]
        assert s["audit_decisions"]==s["root_candidates"]>0 and s["admissible"]<s["root_candidates"]
        if arm=="cached":
            assert s["hits"]>0 and s["root_loop_positions"]==rows["gather"]["frontier"]["root_loop_positions"]


def phase(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        p,plans,req=source.common.config(a,case)
        with source.base.session(a.exp/"compact-vanilla-20261121/vanilla",p) as exact:
            gold=exact({})
        cfg=settings(req,a)
        with source.base.session(a.native,p,plans) as infer:
            rows={arm:[] for arm in cfg}
            for trial in range(4):
                names=list(cfg);names=names[trial:]+names[:trial]
                for arm in names:
                    v=infer(dict(cfg[arm],role_phase=True,audit=False))
                    assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"]
                    if trial:
                        stats=v["multi"]["role_frontier"]
                        rows[arm].append([stats["issuer_ms"],stats["frontier_ms"],stats["root_loop_positions"]])
        report[case]=rows
        print(case,{n:tuple(round(median(i),2) for i in zip(*samples)) for n,samples in rows.items()},flush=True)
        (a.out/"phase.json").write_text(json.dumps(report,indent=1)+"\n")


if __name__=="__main__":
    p=ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--phase",action="store_true")
    a=p.parse_args();a.seed=1703;a.cap=8192;a.repeats=4;a.cases=["conjugate-gradient","3mm"]
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    if a.phase:phase(a)
    else:source.study(a,settings,observe,None)
