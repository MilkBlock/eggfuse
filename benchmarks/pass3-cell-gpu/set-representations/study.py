"""Native Rust Set layout × reader subscription ablation, with honest capacity failures."""
import argparse,json,os,re,subprocess
from pathlib import Path
from statistics import median
from time import perf_counter_ns

ARMS=[(r,s) for r in ('mask','segments','sparse') for s in ('row','instance')]

def read(path):return json.loads(path.read_bytes())
def env(repr_,subs):return dict(os.environ,EGGFUSE_SET_REPR=repr_,EGGFUSE_SET_SUBSCRIPTION=subs)
def execute(binary,program,dest,environ,audit=False):
    args=[str(binary),'--program',str(program),'--output',str(dest)]
    if audit:args.append('--audit-events')
    start=perf_counter_ns();proc=subprocess.run(args,env=environ,capture_output=True,text=True)
    return proc,(perf_counter_ns()-start)/1e6

def schedule(r):return [(x['ruleset'],x['epoch'],x['executed_bindings'],x['changed']) for x in r['steps']]
def graph_events(base,dest):
    for k in ('rhs','writes','resumes','state'):assert read(base/f'{k}.json')==read(dest/f'{k}.json'),(base,dest,k)
    def normalized(path):
        return [[v[:5] if v[0]=='birth' else v for v in events] for events in read(path/'events.json')]
    assert normalized(base)==normalized(dest)
def cardinalities(dest):
    source=read(dest/'state.json')
    return sorted(v['values'][-1].get('value') for v in source['rows'] if v['table'] in ('Cardinality','Size','ExprSet-length'))
def summary(report):
    return dict(runs=len(report['steps']),rhs=sum(x['executed_bindings'] for x in report['steps']),
                memory_helper_runs=sum(s['ruleset']=='memory-helpers' for s in report['steps']),
                memory_helper_rhs=sum(s['executed_bindings'] for s in report['steps'] if s['ruleset']=='memory-helpers'),
                measurements=report.get('set_storage',{}))


def study(a):
    a.out.mkdir(parents=True,exist_ok=a.resume);data=read(a.out/'results.json') if a.resume and (a.out/'results.json').is_file() else {}
    entries={n:(a.sources/n/'program.json',None) for n in ('full','full-probes','helpers','probes','union','dynamic','no-merge')}
    entries.update({n:(a.fixtures/n/'program.json',v) for n,v in read(a.fixtures/'fixtures.json').items()})
    for name,(program,synthetic) in entries.items():
        if name in data:continue
        case=a.out/name
        if a.resume:
            generation=0
            while case.exists():generation+=1;case=a.out/f'{name}-retry-{generation}'
        case.mkdir()
        ref=case/'reference'
        p,_=execute(a.reference,program,ref,os.environ,True)
        if name=='no-merge':assert p.returncode and 'without merge' in (p.stderr+p.stdout)
        elif p.returncode:raise RuntimeError(p.stderr[-6000:])
        reference=None if name=='no-merge' else read(ref/'report.json')
        if reference and not synthetic:
            historical=a.sources/f'study-{name}'/'events'
            if historical.is_dir():graph_events(ref,historical)
        arms={}
        for typ,subs in ARMS:
            arm=f'{typ}-{subs}';dest=case/arm;active=env(typ,subs)
            proc,_=execute(a.runtime,program,dest,active,True)
            if name=='no-merge' or (synthetic and typ=='mask' and synthetic[0]>63):
                cause='without merge' if name=='no-merge' else '63 admitted member'
                assert proc.returncode and cause in (proc.stdout+proc.stderr) and not (dest/'state.json').exists(),(name,arm,proc.stderr[:300])
                arms[arm]=dict(status='expected_failure',cause=cause);continue
            if proc.returncode:raise RuntimeError(f'{name}/{arm}: '+proc.stderr[-6000:])
            rep=read(dest/'report.json');assert schedule(rep)==schedule(reference)
            graph_events(ref,dest);values=cardinalities(dest)
            if synthetic:assert values==[synthetic[1]-1]*synthetic[2],(name,arm,values[:10])
            if name in ('dynamic','union'):assert 1 in values
            arms[arm]=dict(status='accepted',**summary(rep),logical_endpoints=True,cardinality=sorted(set(values)),ms=[],cli_ms=[])
            if (typ,subs) in ARMS:
                cmd=['/usr/bin/time','-l',str(a.heap),str(program)]
                x=subprocess.run(cmd,env=active,capture_output=True,text=True)
                if x.returncode:raise RuntimeError(x.stderr[-2500:])
                arms[arm]['memory']=json.loads(x.stdout)
                rss=re.search(r'(\d+)\s+maximum resident set size',x.stderr)
                if not rss:raise RuntimeError('missing native process RSS')
                arms[arm]['memory']['process_max_rss_bytes']=int(rss.group(1))
        order=[(t,s) for t,s in ARMS if arms[f'{t}-{s}']['status']=='accepted']
        # Every accepted lane appears equally often in each position; alternate directions by rotation.
        for i in range(len(order)):
            rotated=order[i:]+order[:i]
            for typ,subs in rotated if i%2==0 else rotated[::-1]:
                arm=f'{typ}-{subs}';dest=case/f'time-{i}-{arm}'
                proc,ms=execute(a.runtime,program,dest,env(typ,subs))
                if proc.returncode:raise RuntimeError(proc.stderr[-3500:])
                rep=read(dest/'report.json');assert schedule(rep)==schedule(reference) and read(dest/'state.json')==read(ref/'state.json')
                arms[arm]['ms'].append(rep['inference_seconds']*1000);arms[arm]['cli_ms'].append(ms)
        for t,s in order:
            rec=arms[f'{t}-{s}'];rec['median_ms']=median(rec['ms']);rec['median_cli_ms']=median(rec['cli_ms'])
        data[name]=dict(stress=synthetic,source=summary(reference) if reference else None,arms=arms)
        (a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
        print(name,[(k,round(v.get('median_ms',-1),3),v.get('memory',{}).get('peak_heap')) for k,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('runtime','heap','reference','sources','fixtures','out'):p.add_argument(k,type=Path)
    p.add_argument('--resume',action='store_true');study(p.parse_args())
