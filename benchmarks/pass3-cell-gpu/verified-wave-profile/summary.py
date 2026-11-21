"""Attribute each main-thread leaf sample to exactly one scope, and identify native issuer owners."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from runpy import run_path

HERE=Path(__file__).resolve().parent
prior=run_path(str(HERE.parent/"witness-production-profile/attribute.py"))


def report(path):
    base=prior["attribute"](path)
    scope=Counter()
    stack=[]
    def close():
        indent,weight,children,name=stack.pop()
        cost=weight-children
        if not cost:
            return
        names=[n[3] for n in stack]+[name]
        if prior["classify"](names)!=("execute","multi_witness"):
            return
        for ancestor in reversed(names):
            match=re.search(r'ordinary_witness::(?:Store|State|Programs|Frontier)::([A-Za-z_0-9]+)',ancestor)
            if match:
                scope[match.group(1)]+=cost
                break
        else:
            scope["other_multi"]+=cost
    main=False
    body=path.read_text().split("Call graph:\n")[1].split("\nTotal number")[0]
    for line in body.splitlines():
        m=re.match(r'^([ |+!:]*)\s*(\d+)\s+(.+)$',line)
        if not m:continue
        prefix,count,tail=m.groups()
        depth=len(prefix)
        while stack and stack[-1][0]>=depth:
            close()
        name=tail.partition("  (in ")[0].strip()
        if 'Thread_' in name and not stack:
            main='main-thread' in name
        if not main:continue
        if stack:stack[-1][2]+=int(count)
        stack.append([depth,int(count),0,name])
    while stack: close()
    assert sum(scope.values())==base['categories']['execute'].get('multi_witness',0)
    return dict(main=base['main_thread_samples'],categories=base['categories'],multi=scope,
                sample_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    datasets=json.loads((a.capture/"summary.json").read_bytes())
    result={case:{name:{**report(a.capture/f"{case}-{name}.sample"),"request":v} for name,v in pair.items()}
            for case,pair in datasets.items()}
    a.output.write_text(json.dumps(result,indent=1)+"\n")
    for case,v in result.items():
        print(case,sorted(v["packed"]["multi"].items(),key=lambda x:-x[1])[:12])
