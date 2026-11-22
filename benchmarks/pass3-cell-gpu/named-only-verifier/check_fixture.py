"""Native receiver regressions for the compiled ripsat-strict-acceptance/local-equality.egg."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import subprocess
from accept import evaluate


def check(verifier, reference, program, join):
    def packet(run,rule,cell,version):
        return dict(run=run,rule=rule,parents=[[{'Fact':dict(cell=cell,op=0)},version]])
    # Known fixture allocation, two Seed inputs followed by two Pair outputs.
    seeds=[packet(1,2,c,0) for c in (4,5)]
    children=[packet(2,r,c,1) for r in (0,1) for c in (6,7)]
    cases=[
        ('explicit',seeds+children,5,1,6,'difference'),
        ('empty',[],0,0,0,'difference'),
        ('missing',[dict(run=1,rule=2,parents=[])],0,1,0,'difference'),
        ('extra',[dict(run=1,rule=2,parents=seeds[0]['parents']*2)],0,1,0,'difference'),
        ('wrong-version',[packet(1,2,4,1)],0,1,1,'difference'),
        ('wrong-table',[packet(1,2,1,0)],0,1,1,'difference'),
        ('absent-address',[packet(1,2,999999,0)],0,1,1,'difference'),
        ('omit-successors',seeds,2,0,2,'difference'),
    ]
    with TemporaryDirectory() as directory:
        plans=Path(directory)/'empty-plans.json'
        plans.write_text('[]')
        for name,stream,accepted,rejected,reads,status in cases:
            result=evaluate(verifier,reference,program,plans,stream)
            if [result[k] for k in ('accepted','rejected','named_reads','status')] != [accepted,rejected,reads,status]:
                raise ValueError((name,result))
            if name == 'explicit' and {k for k,ok in result['checks'].items() if not ok} != {'resumes','events'}:
                raise ValueError('cross-stage reference divergence changed')
            print(name,result)
        addresses = [packet(1,0,c,0)['parents'][0] for c in (1,2)]
        for n,expected,reads,status in [(2,1,2,'pass'),(1,0,0,'difference')]:
            row = dict(run=1,rule=0,parents=addresses[:n])
            result = evaluate(verifier,reference,join,plans,[row])
            if (result['accepted'],result['named_reads'],result['status']) != (expected,reads,status):
                raise ValueError(('independent join',n,result))
            print('independent join',n,result)
    for request in ({'baseline':True}, {'multi_residual':True}, [dict(seeds[0],search=True)]):
        proc=subprocess.run([verifier,program],input=json.dumps(request),text=True,capture_output=True)
        if proc.returncode==0:
            raise ValueError('accepted a search/configuration request')


if __name__=='__main__':
    check(*map(Path,sys.argv[1:]))
