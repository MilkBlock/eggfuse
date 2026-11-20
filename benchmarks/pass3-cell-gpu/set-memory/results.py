"""Validate isolated device exports and summarize CPU/GPU, native and negative controls."""
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from collections import Counter
from pathlib import Path
import numpy as np

GPU=Path(__file__).resolve().parents[1];sys.path.insert(0,str(GPU))
from audit import graph
from codec import canonical

def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def isolated(trial,image,weights,ports,root):
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        for n in ('device.npz','device.json','export-schema.json'):shutil.copyfile(image/n,tmp/n)
        shutil.copyfile(weights,tmp/'address.pt');shutil.copyfile(ports,tmp/'ports.pt')
        subprocess.run([sys.executable,GPU/'isolated_check.py',tmp,root,'unused','--worker'],check=True)
        seen=read(tmp/'opened.json')
        assert set(seen)=={'device.npz','device.json','export-schema.json','address.pt','ports.pt'}
        ref=read(trial/'cpu/state.json');packet=read(image/'ingress.json')
        with np.load(trial/'gpu/output.npz') as z:
            eq,exact=graph(z['rows'],z['meta'],ref,packet,read(trial/'gpu/run.json')['strings'],z['parents'],z['set_members'])
            assert exact
        final=read(tmp/'result/state.json')
        def ids(v):
            if 'eq' in v:return dict(sort=v['sort'],eq=eq[v['sort'],int(v['eq'][5:-1])])
            if 'elements' in v:
                return dict(sort=v['sort'],elements=sorted(map(ids,v['elements']),key=lambda e:int(e['eq'][5:-1])))
            return v
        rows=[dict(r,values=list(map(ids,r['values']))) for r in final['rows']]
        assert Counter(map(canonical,rows))==Counter(map(canonical,ref['rows']))
        anchors=[dict(a,now=eq[a['sort'],int(a['now'][5:-1])]) for a in final['anchors']]
        assert Counter(map(canonical,anchors))==Counter(map(canonical,ref['anchors']))
        return dict(opened=seen,export_sha256=sha(tmp/'result/state.json'),rows=len(rows))

def summarize(root,weights,ports,timing,out):
    cases={}
    for name in ('full','full-probes','helpers','probes','union','dynamic'):
        trial=root/f'study-{name}';gpu=trial/'gpu';cpu=trial/'cpu'
        evidence=read(gpu/'check.json');assert evidence['acceptance']=='pass'
        report=read(cpu/'report.json');program=read(root/name/'program.json')
        sets=read(gpu/'run.json')['state'][56:65]
        metrics=dict(source_sha256=sha(root/name/'source.egg'),program_sha256=program['sha256'],
                     input=sha(trial/'input/device.npz'),device_trace=sha(gpu/'output.npz'),audit=evidence,
                     set_counts=dict(zip(('empty','of','insert','intersect','union','length','collapsed_bits','repair_columns','changed_columns'),sets)),
                     helper_runs=sum(s['ruleset']=='memory-helpers' for s in report['steps']),
                     helper_rhs=sum(s['executed_bindings'] for s in report['steps'] if s['ruleset']=='memory-helpers'),
                     writes=sum(n for n,_ in read(cpu/'writes.json')))
        if name in ('full','full-probes','union','dynamic'):
            metrics['isolated']=isolated(trial,trial/'input',weights,ports,root)
        if name in ('union','dynamic'):
            tables=program['recipe']['tables']
            metrics['integer_writes']=[dict(run=i,table=tables[e[3]]['name'],old=e[-2],new=e[-1]) for i,events in
                enumerate(read(trial/'events/events.json'),1) for e in events if e[0]=='write']
        cases[name]=metrics
    assert cases['full']['helper_rhs'] and not any(cases['full']['set_counts'][k] for k in ('insert','intersect','union','length'))
    assert all(cases['full-probes']['set_counts'][k]>0 for k in ('insert','intersect','union','length'))
    assert [(v['old'],v['new']) for v in cases['dynamic']['integer_writes']]==[(None,{'Int':2}),({'Int':2},{'Int':1})]
    cpu=read(root/'conflict-cpu/failure.json');gpu=read(root/'conflict-gpu/run.json')
    assert cpu['error']=='conflicting function ExprSet-length without merge' and gpu['fault']==12
    assert len(cpu['completed_steps'])==gpu['completed']==3
    result=dict(cases=cases,timing=read(timing/'timing.json'),negative=dict(cpu=cpu['error'],gpu_fault=gpu['fault'],
                completed_before_fault=gpu['completed']),native_checked_source=sha(root/'native-check.egg'),
                native_snapshot=sha(root/'native-check.json'),weights_sha256=sha(weights),ports_sha256=sha(ports))
    if (root/'capacity.json').exists(): result['capacity_control']=read(root/'capacity.json')
    out.write_text(json.dumps(result,indent=1)+'\n')

if __name__=='__main__':
    q=argparse.ArgumentParser()
    for k in ('root','weights','ports','timing','out'):q.add_argument(k,type=Path)
    a=q.parse_args();summarize(a.root,a.weights,a.ports,a.timing,a.out)
