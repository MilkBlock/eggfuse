"""Separate partial observation from training error on the fixed all-compose stream."""
import argparse
from collections import defaultdict
import json
from pathlib import Path


def report(folder):
    programs=json.loads((folder/"stream.json").read_bytes())
    fields,*raw=[json.loads(l) for l in (folder/"actions.jsonl").read_text().splitlines()]
    actions=[dict(zip(fields,r)) for r in raw]
    prepared=json.loads((Path(__file__).resolve().parent.parent/"owner-action-policy/policies.json").read_bytes())["regression"]
    natural=json.loads((folder/"natural-regression.json").read_bytes())
    def policy(p,x):
        score=p["intercept"]
        for weight,count in zip(p["weights"],x):score+=weight*count
        return score>0
    results={}
    for case,arms in programs.items():
        rows=[actions[i] for i in arms["defer/merge"]["actions"]]
        totals=defaultdict(list)
        for r in rows:totals[tuple(r["features"])].append(r["saved_bytes"])
        gain=lambda p:sum(r["saved_bytes"] for r in rows if policy(p,r["features"]))
        results[case]=dict(moves=len(rows),features=len(totals),positive=sum(r["saved_bytes"]>0 for r in rows),
                           negative=sum(r["saved_bytes"]<0 for r in rows),net=sum(r["saved_bytes"] for r in rows),
                           mixed_sign_features=sum(min(g)<0<max(g) for g in totals.values()),
                           positive_only=sum(max(0,r["saved_bytes"]) for r in rows),
                           best_by_features=sum(max(0,sum(g)) for g in totals.values()),
                           prepared_gate=gain(prepared),natural_gate=gain(natural))
    return results


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder",type=Path)
    args=p.parse_args()
    (args.folder/"returns.json").write_text(json.dumps(report(args.folder),indent=1)+"\n")
