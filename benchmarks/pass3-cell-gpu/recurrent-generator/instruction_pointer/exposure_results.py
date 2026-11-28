"""Export native execution curves, same-state evidence and training lineage as auditable text."""
import argparse
import csv
import gzip
import hashlib
import json
import pickle
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from int_parameters import digest


def read(path):
    return json.loads(path.read_text())


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def table(path, rows):
    if rows:
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,list(dict.fromkeys(k for r in rows for k in r)))
            w.writeheader()
            w.writerows(rows)


def export(out, dest):
    dest.mkdir(exist_ok=True,parents=True)
    d=out.parent/"full-ce-scaling"
    for file in ("corpora.json","split.json"):
        if (out/file).exists():
            (dest/file).write_text(json.dumps(read(out/file),sort_keys=True,indent=2)+"\n")
    db=sqlite3.connect(out/"native.sqlite")
    def records(kind):
        return [(key,json.loads(gzip.decompress(blob))) for key,blob in
                db.execute("select key,data from evidence where kind=? order by key",(kind,))]
    failures = []
    for _, data in records("native_panic"):
        failures.append(dict(**data["condition"], mode="trial", budget=data["cap"],
                             observed_replies=len(data["observed_replies"]), stderr=data["stderr"]))
    failures.extend(data for _, data in records("failed_budget"))
    table(dest/"native-failures.csv", failures)
    fits=[]
    curves=[]
    files=[]
    checks = []
    starts = [d/"fits"/f"{arm}-s{seed}-t100000.json" for arm,seed in
              (("local",71),("center",71),("layer03",71),("local",113))]
    fits_paths=starts+sorted(out.glob("*/*-t*.json"))
    probes=dict(records("probes"))
    for file in fits_paths:
        r=read(file)
        name= file.stem if file in starts else file.parent.name+"/"+file.stem
        probe=probes.get(name)
        values=dict(model=name,weights_sha256=sha(file.with_suffix(".pt")),**{k:r[k] for k in (
            "registered","forward_observed","connected","state_pool","states","targets","verified_distinct_effects",
            "exposures","steps","seconds","tokens_per_s","train_ce")})
        previous=max((x for x in r["learning_curve"] if x["exposures"] in
                      (100000,250000,500000) and x["exposures"]<r["exposures"]),
                     key=lambda x:x["exposures"],default=None)
        base=previous or {"exposures":0,"seconds":0,"steps":0,"cumulative_train_ce":0}
        dt=r["seconds"]-base["seconds"]
        n=r["exposures"]-base["exposures"]
        values.update(interval_tokens=n,interval_seconds=dt,interval_tokens_per_s=n/dt,
                      interval_train_ce=(r["exposures"]*r["train_ce"]-base["exposures"]*base["cumulative_train_ce"])/n)
        if probe:
            rows=probe["binding"]
            values.update(validation_ce=sum(z["targets"]*z["ce"] for z in rows)/sum(z["targets"] for z in rows),
                          validation_native_target_hits=sum(z["known_hits"] for z in rows)/sum(z["slots"] for z in rows))
            for g in sorted({row["group"] for row in rows}):
                items=[row for row in rows if row["group"]==g]
                values[g+"_known_hits"]=sum(z["known_hits"] for z in items)/sum(z["slots"] for z in items)
            siblings=defaultdict(list)
            for z in probe["higher"]:
                siblings[z["program"]].append(z["wins"])
            values["higher_both_siblings_correct"]=sum(all(z) for z in siblings.values())
            values["higher_native_pairs"]=len(siblings)
        fits.append(values)
        for i in r["learning_curve"]:
            if i["exposures"]>base["exposures"]:
                curves.append(dict(model=name,**i))
        checks.append(dict(model=name,config=r["config"],sources=r["sources"],archive_sha256=r["archive_sha"],
                           weights_sha256=values["weights_sha256"],model_file=str(file.with_suffix(".pt").relative_to(out.parent))))
    table(dest/"training.csv",fits)
    table(dest/"learning-curve.csv",curves)
    table(dest/"budget-curves.csv",[dict(row,statuses=json.dumps(row["statuses"],sort_keys=True)) for _,rs in records("curve") for row in rs])
    schedules=[]
    anchors=[]
    historical=[]
    for _,v in records("trial"):
        c,r=v["condition"],v["r"]
        if v["cap"] == 256:
            req = v["requests"]
            first = next((i for i,q in enumerate(req) if q["ops"]>0),None)
            if first is not None:
                anchors.append(dict(**c,total_paid=len(req),first_paid=first+1,first_ops=req[first]["ops"],
                                    first_run=req[first]["run"],first_template=req[first]["tid"],
                                    later_paid=len(req)-first-1,later_ops=sum(q["ops"] for q in req[first+1:])))
        if c["model"]=="history" and c["unique"] and v["cap"] in (16,32,64,128,256):
            old=out.parent/"continuous-cell-stream"/f'{c["case"]}-{v["cap"]}-{c["seed"]}-history.json'
            if old.exists():
                prior=read(old)
                same=(prior["graph"],prior["facts"],prior["ops"],prior["paid"])==(r["graph"],r["facts"],r["ops"],r["stats"]["paid"])
                if not same:
                    raise ValueError("historical stream parity failed: "+old.name)
                historical.append(dict(program=c["case"],seed=c["seed"],cap=v["cap"],ledger=old.name,
                                       graph=r["graph"],matched=same))
        if v["cap"] is None:
            req=v["requests"]
            first=next((i for i,x in enumerate(req) if x["ops"]>0),None)
            schedules.append(dict(**c,paid=len(req),first=first+1 if first is not None else None,
                after_first_ops=sum(x["ops"] for x in req[first+1:]) if first is not None else None,
                covered=r["covered"],reference=r["reference"],coverage=r["coverage"],ops=r["ops"],ept=r["ept"],
                eps=r["eps"],wall=r["wall"],graph=r["graph"],pending=r["pending"],
                higher_completed=r["stats"].get("higher_completed",0),higher_selected=r["stats"].get("higher_selected",0),
                statuses=json.dumps(r["receipts"],sort_keys=True)))
    table(dest/"full-schedule.csv",schedules)
    table(dest/"first-success.csv",anchors)
    table(dest/"historical-parity.csv",historical)
    table(dest/"paired-timing.csv",[dict(row,facts=json.dumps(row["facts"])) for _,rows in records("timing") for row in rows])
    (dest/"models.json").write_text(json.dumps(checks,indent=2)+"\n")
    (dest/"first-divergence.json").write_text(json.dumps([v for _,v in records("divergence")],indent=2)+"\n")
    # Report all audited singleton forks including failures and possible equivalence aliases.
    counts=Counter()
    fork_states=defaultdict(dict)
    for p in sorted(out.glob("fork-*.pkl.gz")):
        with gzip.open(p,"rb") as f:
            tape=pickle.load(f)
        for e in tape["examples"]:
            for q in e["table"]:
                fork_states[(tape["case"],e["sh"])][q["token"]]=q
                t=(tape["case"],tape["source"],q["evidence"]["status"],q["hard"],q["ordinary"],
                   q["named_repeat"],q["effect"] is not None)
                counts[t]+=1
    table(dest/"native-forks.csv",[dict(program=k[0],behavior=k[1],receipt=k[2],proposed_hard=k[3],
                   sampled_ordinary=k[4],previously_issued_name=k[5],verified_new_effect=k[6],count=n)
                   for k,n in sorted(counts.items())])
    by_program=defaultdict(Counter)
    for (case,_), names in fork_states.items():
        totals=by_program[case]
        outcomes=set()
        positive=0
        totals["audited_states"]+=1
        for q in names.values():
            totals["verified_state_names"]+=1
            totals["previously_submitted_name"]+=q["named_repeat"]
            if q["effect"]:
                positive+=1
                outcomes.add((q["graph"],tuple(q["gain"]),tuple(q["lost"]),q["evidence"]["ops"]))
                totals["productive_reissues"]+=q["named_repeat"]
        totals["different_positive_state_outcomes"]+=len(outcomes)
        totals["different_names_identical_observed_positive_outcome"]+=positive-len(outcomes)
    table(dest/"fork-identity.csv",[dict(program=k,**v) for k,v in sorted(by_program.items())])
    gains=Counter()
    selected=[]
    for group in ("B","C","D"):
        path=out/(group+"-data.pkl.gz")
        if not path.exists():
            continue
        with gzip.open(path,"rb") as f:
            data=pickle.load(f)
        for case,s,(t,rs),e in data:
            gains[(group,case,len(rs))]+=1
            sh=digest(s)
            observation=fork_states[(case,sh)][(t,rs)]
            selected.append(dict(arm=group,program=case,state=sh,rule=t,parents=len(rs),
                                 complete_token_probability=observation["p"],signed_ops=observation["evidence"]["ops"],
                                 reference_gains=len(observation["gain"]),outcome=e))
    table(dest/"added-targets.csv",[dict(arm=k[0],program=k[1],parents=k[2],states=n) for k,n in sorted(gains.items())])
    table(dest/"added-state-evidence.csv",selected)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("out",type=Path)
    parser.add_argument("dest",type=Path)
    a=parser.parse_args()
    export(a.out,a.dest)
