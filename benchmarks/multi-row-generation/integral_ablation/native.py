"""Run the three original rulesets with actual local/external unions in Rust Cell CPU."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
TABLES=('IAnchor','ICompared','ITagged','IResult')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(binary,inputs,out):
    declarations=(HERE/'source.egg').read_text()
    fixtures=[]
    for c in json.loads(inputs.read_text())['cases']:
        if c['metadata']['rule'] not in (134,135,143,266,267,580) or 'external-' not in c['id']:continue
        ports=[16*owner+p for owner in (0,1) for p in c['metadata']['public']]
        source,schedule=c['source'].rsplit('(run-schedule',1)
        local,bridge,observe=re.findall(r'\(run ([^() ]+)\)',schedule)
        assert bridge=='external' and observe=='observe'
        q='\n'.join(f'(IQuery {l} {r})' for l,r in itertools.product(ports,repeat=2))
        seq=f'(run-schedule (seq (saturate (run ia)) (run {local}) (saturate (run ib)) (run external) (saturate (run ic))))'
        fixtures.append(dict(id=c['id'],source='\n'.join((source,declarations,q,seq))))
    assert len(fixtures)==54
    verified={};total_steps=0
    with tempfile.TemporaryDirectory() as temp:
        inp,output=[Path(temp)/s for s in ('cases.json','graphs.json')]
        for first in range(0,len(fixtures),6):
            inp.write_text(json.dumps(dict(cases=fixtures[first:first+6])))
            subprocess.run([binary,inp,output],check=True)
            for case in json.loads(output.read_text())['cases']:
                snapshots={}
                times=Counter()
                for step,bound in zip(case['steps'],case['boundaries'],strict=True):
                    label=step['ruleset'];total_steps+=1;times[label]+=1
                    if label not in ('ia','ib','ic'):continue
                    rows={s:set() for s in TABLES};values={}
                    for row in bound['graph']['rows']:
                        if row['subsumed']:continue
                        vals=row['values'];name=row['table']
                        if name=='Observe':values[vals[0]['value']]=vals[1]['eq']
                        if name in rows:rows[name].add(tuple(v['value'] for v in vals[:-1]))
                    snapshots[label]=(rows,values)
                bvals=snapshots['ib'][1];cvals=snapshots['ic'][1]
                reads=snapshots['ia'][0]['IAnchor'];assert len(reads)==36
                old={(i,j,int(bvals[i]==bvals[j])) for i,j in reads}
                final={(i,j,oldval,int(cvals[i]==cvals[j])) for i,j,oldval in old}
                for s,wanted in [('ia',[reads,set(),set(),set()]),('ib',[reads,old,old,set()]),('ic',[reads,old,old,final])]:
                    if [snapshots[s][0][k] for k in TABLES]!=wanted:raise ValueError((case['id'],s))
                verified[case['id']]=dict(sweeps=times,final_signature=hashlib.sha256(json.dumps(sorted(final)).encode()).hexdigest(),
                        changed_after_b=sum(o!=v for _,_,o,v in final))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(binary_sha256=sha(binary),base_inputs_sha256=sha(inputs),source_sha256=sha(HERE/'source.egg'),
        cases=len(verified),actual_runs=total_steps,results=verified),indent=1)+'\n')
    print(len(verified),total_steps)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('binary','inputs','out'):p.add_argument(key,type=Path)
    a=p.parse_args();main(a.binary.resolve(),a.inputs,a.out)
