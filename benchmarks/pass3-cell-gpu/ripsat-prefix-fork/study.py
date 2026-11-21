"""Fork one fresh publication after its successful RHS, retaining every other permit."""
import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/"ripsat-block-verifier/study.py"))
study=base["study"]


def signature(row):
    # Source ordinal, rule, template, version, physical parents and bound inputs.
    return [row[0],*row[3:]]


def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def audit(a,case):
    p,plans,req,plan=study["setup"](a,case)
    def config(root=None):
        s=dict(plan,block_verifier=True,receipt_scan=2,
               issuance_actor=dict(mode="greedy",seed=0,weights=base["weights"]))
        if root is not None:s["withhold_root"]=root
        return study["matrix"]["cfg"](req,s,True)
    with study["src"].base.session(a.native,p,plans) as run:
        full=run(config())
        roots=full["root_recipe"]["commits"]
        byserial={r[2]:r for r in roots}
        sig=full["strict_named"]
        def internal(v):
            ids={x[0] for x in v["strict_named"]["signed_commits"]}
            return {r[0] for r in v["root_recipe"]["commits"] if r[2] in ids}
        owned=internal(full)
        results=[]
        for link in sig["set_commits"][:a.limit]:
            root=link["root"]
            middle=byserial[link["middle"]]
            terminal=byserial[link["consumer"]]
            prefix=run(config(root))
            assert "source_error" not in prefix
            for k in ("rhs","writes","resumes","runs","state_sha","schedule"):
                assert prefix[k]==full[k],(case,k)
            other=prefix["root_recipe"]["commits"]
            assert roots[:middle[0]]==other[:middle[0]]
            assert len(roots)==len(other)
            for x,y in zip(roots,other):
                assert signature(x)==signature(y)
            assert owned-internal(prefix)=={terminal[0]} and not internal(prefix)-owned
            assert study["packets"](prefix)==study["packets"](full)+1
            assert prefix["strict_named"]["set_publication"]["withheld"]==1
            siblings=[byserial[s["consumer"]][0] for s in sig["set_commits"]
                      if s["consumer_run"]==link["consumer_run"] and s["root"]!=root]
            results.append(dict(root=root,middle=middle[0],terminal=terminal[0],
                fork_run=link["middle_run"],consumer_run=link["consumer_run"],terminal_rule=terminal[3],
                fact=link["fact"],version=link["version"],other_internal_terminals_same_run=siblings,
                binding_sha=digest(signature(terminal)),extra_external_proposals=1))
        return dict(source_rhs=len(roots),eligible=len(sig["set_commits"]),forks=results)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--limit",type=int,default=3)
    a=p.parse_args()
    report={}
    for case in ("sum-bits","3mm"):
        report[case]=audit(a,case)
        (a.out/"pairs.json").write_text(json.dumps(report,indent=2)+"\n")
        print(case,len(report[case]["forks"]),flush=True)
