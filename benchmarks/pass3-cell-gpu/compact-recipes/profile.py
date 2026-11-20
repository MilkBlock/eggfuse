"""Sample repeated resident passes; keep only CPU stacks inside native inference for attribution."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

FRAME=re.compile(r'^(?P<tree>[\s+!:|]+)(?P<n>\d+)\s+(?P<name>.+?)\s+(?:\(in |\+)')
def analyze(path):
    stack=[];leaves=Counter();groups=Counter();hits=0
    # The tree contains inclusive frame counts. Subtract child samples before aggregating leaves.
    def finish():
        nonlocal hits
        depth,n,function,remaining,inside,trail=stack.pop()
        if remaining<0:raise ValueError(f'inconsistent sample depth for {function}')
        if not inside or not remaining:return
        hits+=remaining;leaves[function]+=remaining
        category='other source execution'
        for name,markers in [
            ('single-witness generator/verifier',['single_witness','single_scores']),
            ('multi-witness generator/verifier',['ordinary_witness','ordinary_shortlist']),
            ('RHS / root and merge recipes',['apply_owned','joint_root','joint_merge']),
            ('rebuild / repair',['::repair','::rebuild']),
            ('native search and incremental matching',['::matches','::search','::answers','::update_query'])]:
            if any(m in f for f in trail for m in markers):category=name;break
        groups[category]+=remaining
    for line in path.read_text().split('Call graph:',1)[-1].split('Total number in stack',1)[0].splitlines():
        m=FRAME.match(line)
        if not m:continue
        depth=len(m['tree'])
        while stack and stack[-1][0]>=depth:finish()
        n=int(m['n']);function=m['name']
        if stack:stack[-1][3]-=n
        inside=(stack and stack[-1][4]) or ('Executor::execute' in function)
        trail=(*stack[-1][5],function) if stack else (function,)
        stack.append([depth,n,function,n,bool(inside),trail])
    while stack:finish()
    return dict(inference_samples=hits,exclusive_groups=dict(groups),exclusive_leaf=leaves.most_common(32))

def profile(binary,bundle,root_file,out,variant):
    args=[binary,bundle/'program.json']
    if variant!='vanilla':args.append(bundle/'plans.json')
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    req={}
    if variant!='vanilla':
        req=json.loads((bundle/'request.json').read_bytes())
        for field in ('root_config','merge_config','multi_weights','single_config'):
            req[field]=str(bundle/req[field])
        req['root_config']=str(root_file)
    def run():
        proc.stdin.write(json.dumps(req).encode()+b'\n');proc.stdin.flush()
        raw=proc.stdout.readline()
        if not raw:raise RuntimeError('worker exited before reporting')
        record=json.loads(raw)
        if 'source_error' in record:raise RuntimeError(record['source_error'])
        return record['state_sha']
    try:
        state=run();sample_file=out/f'{variant}.txt'
        sampler=subprocess.Popen(['/usr/bin/sample',str(proc.pid),'5','1','-file',sample_file])
        shots=0
        while sampler.poll() is None:
            if run()!=state:raise ValueError('profiled pass diverged')
            shots+=1
        if sampler.returncode:raise RuntimeError('sample failed')
        result=analyze(sample_file)
        if result['inference_samples']<50:raise ValueError(f'no usable inference stack in {sample_file}')
        return dict(result,state_sha=state,completed=shots)
    finally:
        proc.stdin.close();proc.wait()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('native','vanilla','bundle','out'):p.add_argument(name,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((a.bundle/'root.json').read_bytes());config['encoding']='resident'
    root=a.out/'root.json';root.write_text(json.dumps(config))
    report={}
    for variant,exe in [('vanilla',a.vanilla),('resident',a.native)]:
        report[variant]=profile(exe,a.bundle,root,a.out,variant)
        (a.out/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
