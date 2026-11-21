"""Compare the deployed policies on fresh RSS processes and a withheld terminal port."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
study = run_path(str(HERE/"study.py"))
base = study["base"]
rss = run_path(str(HERE.parent/"ripsat-publication-matrix/rss.py"))


def measure(a, case):
    p,plans,req,plan=base["setup"](a,case)
    w=json.loads(a.checkpoint.read_text())["weights"]
    prior=json.loads((HERE.parent/"ripsat-issuance-rl/actor.json").read_text())["weights"]
    arms={}
    growth=json.loads(rss["cal_file"].read_text())[case]["thresholds_kib"]["0.9"][1]
    with base["src"].base.session(a.native,p,plans) as run:
        for name,policy in [("previous",dict(plan,block_verifier=True,receipt_scan=2,
            issuance_actor=dict(weights=prior,mode="greedy",seed=0))),("greedy",study["spec"](plan,"greedy",w))]:
            cfg=study["cfg"](req,policy)
            v=run(cfg)
            s=v["strict_named"]
            arms[name]=dict(cfg=cfg,trials=[],want=dict(runs=v["runs"],state_sha=v["state_sha"],
                emitted=v["root_recipe"]["emitted"],internal=s["counts"]["source_commits"],
                set_internal=s["set_publication"]["confirmed"]),header_checks=v["root_recipe"]["root_header_checks"],
                receipt_reads=s["receipt_scan"]["row_reads"])
        if a.verifier_clock:
            totals={name:[] for name in arms}
            for lap in range(7):
                for name in (list(arms) if lap%2 else reversed(arms)):
                    cfg=arms[name]["cfg"]
                    v=run(dict(cfg,rows=dict(cfg["rows"],profile=True)))
                    assert v["state_sha"]==arms[name]["want"]["state_sha"]
                    if lap: totals[name].append(v["single"]["adaptive_rows"]["phase_ns"][3])
            return totals
        stale=run(study["cfg"](req,dict(policy,set_fault="stale"),True))
        normal=run(study["cfg"](req,policy,True))
        for k in ("runs","state_sha","rhs","writes","resumes","schedule"):
            assert stale[k]==normal[k]
        assert stale["strict_named"]["set_publication"]["confirmed"]==0
        # Removing a terminal can expose another external root, whose policy
        # can in turn issue a different continuation. Recount all endpoints.
        delta=base["packets"](stale)-base["packets"](normal)
        assert delta==arms["greedy"]["want"]["internal"]-len(stale["strict_named"]["signed_commits"])
    for lap in range(4):
        for k in (list(arms) if lap%2 else reversed(arms)):
            arm=arms[k]
            pair={b:rss["one"](a.native,p,plans,arm["cfg"],b,arm["want"])
                  for b in ((True,False) if lap%2 else (False,True))}
            trace=pair[True]["trace"]
            arm["trials"].append(dict(growth=rss["crossing"](trace,trace[0][1]+growth),plain_ms=pair[False]["ms"]))
    for arm in arms.values():del arm["cfg"]
    return dict(arms=arms,growth_kib=growth,stale_packet_delta=delta)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","checkpoint","output"):parser.add_argument(key,type=Path)
    parser.add_argument("--verifier-clock",action="store_true")
    a=parser.parse_args()
    a.out=a.output.parent
    out={}
    for case in ("sum-bits","3mm"):
        out[case]=measure(a,case)
        a.output.write_text(json.dumps(out,indent=2)+"\n")
