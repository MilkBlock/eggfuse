"""Audit all measured trajectories before reporting segmented timestamp samples."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median
from xml.etree import ElementTree

import numpy as np

GROUP={'clear_counts':'control','next_run':'control','entry_matches':'entry',
       'emit_tokens':'tokens','sort_unique':'tokens','apply_rhs':'rhs','finish_repair':'repair',
       'spine_matches':'spine','publish_spine':'spine'}


def read(p):return json.loads(p.read_text())


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def duration(spans):
    start=end=total=0
    for a,b in sorted(spans):
        if a>end:total+=end-start;start=a
        end=max(b,end)
    return total+end-start


def compare(key,got,want,meta,columns):
    if key=='rhs':
        np.testing.assert_array_equal(want[:,:2],got[:,:2])
        np.testing.assert_array_equal(want[:,4:],got[:,4:])
    elif key=='rows':
        for t,width in enumerate(columns):
            at=meta[:,0]==t
            np.testing.assert_array_equal(want[at,:width],got[at,:width])
    else:
        np.testing.assert_array_equal(got,want,err_msg=key)


def check_mps(folder,reference,columns):
    fields=('rhs','writes','resumes','runs','meta','parents','rows')
    with np.load(reference/'output.npz') as old,np.load(folder/'output.npz') as new:
        meta=old['meta']
        for k in fields:compare(k,new[k],old[k],meta,columns)
    return digest(folder/'output.npz')


def inspect_device(folder,reference,steps,columns):
    data=read(folder/'timing.json');n=data['completed']
    if len(steps)!=n:raise ValueError((folder,n))
    # Independently of the resident auditor, compare the native timing replay to
    # the original fully validated run, including the stored class parent map.
    with np.load(reference/'output.npz',allow_pickle=False) as old:
        for key in ('rhs','writes','resumes','runs','meta','parents','rows'):
            want=old[key];got=np.fromfile(folder/(key+'.bin'),want.dtype).reshape(want.shape)
            compare(key,got,want,old['meta'],columns)
    phases=defaultdict(list);by_set=defaultdict(Counter);spans=[]
    counts=Counter();tail=0
    for s in data['samples']:
        if s['end']-s['start']!=s['ns']:raise ValueError('counter interval mismatch')
        ms=s['ns']/1e6
        if s['run']>n:tail+=ms;continue
        name=s['name'];phases[name].append(ms);counts[s['run']]+=1
        spans.append((s['start'],s['end']))
        by_set[name][steps[s['run']-1]['ruleset']]+=ms
    required={'base':4,'detail':9}[data['mode']]
    if len(counts)!=n or set(counts.values())!={required}:raise ValueError('missing encoder sample')
    sums={k:sum(v) for k,v in phases.items()};total=sum(sums.values());groups=Counter()
    for k,ms in sums.items():groups[GROUP.get(k,k)]+=ms
    return dict(runs=n,phases_ms=sums,groups_ms=groups,group_pct={k:100*v/total for k,v in groups.items()},
                per_encoder={k:dict(samples=len(v),median_us=median(v)*1000,p95_us=float(np.percentile(v,95))*1000,
                                    max_us=max(v)*1000) for k,v in phases.items()},phase_sum_ms=total,
                interval_union_ms=duration(spans)/1e6,budget_padding_ms=tail,
                gpu_command_ms=sum(c['gpuMS'] for c in data['commands']),diagnostic_wall_ms=data['wallMS'],
                hot_rulesets={k:v.most_common(6) for k,v in by_set.items()},
                timing_sha256=digest(folder/'timing.json'),verified=True)


def system_trace(folder,name,reference,skill):
    import sys
    from importlib.util import spec_from_file_location,module_from_spec
    def load(n):
        spec=spec_from_file_location('trace_'+n,skill/'scripts'/f'{n}.py')
        m=module_from_spec(spec);spec.loader.exec_module(m);return m
    sys.path.insert(0,str(skill/'scripts'))
    parser=load('report');record=load('profile')
    problems=record.issues(folder/f'{name}.trace')
    if parser.trace_problems(problems):raise ValueError(problems)
    toc=ElementTree.parse(folder/f'{name}-toc.xml');pid=toc.find('.//target/process').attrib['pid']
    data=parser.tables(folder/f'{name}-gpu.xml')
    selected=[r for t in data for r in t['rows'] if r['process']['fmt'].endswith(f'({pid})') and
              r['state']['raw']=='Active' and int(r['event-depth']['raw'])==0]
    if not selected:raise ValueError('missing live target samples')
    spans=[(int(s['start']['raw']),int(s['start']['raw'])+int(s['duration']['raw'])) for s in selected]
    if digest(folder/f'xctrace-{name}/state.json')!=digest(reference/'state.json'):raise ValueError('xctrace endpoint')
    return dict(target_pid=int(pid),segments=len(spans),observed_span_ms=(max(b for _,b in spans)-min(a for a,_ in spans))/1e6,
                target_gpu_active_ms=duration(spans)/1e6,issues=problems,xml_sha256=digest(folder/f'{name}-gpu.xml'),
                template=toc.findtext('.//summary/template-name'))


def report(folder,root,skill,out):
    cold=read(folder/'cold-final.json');warm=read(folder/'warm-paired.json');cases={}
    for n in ('sum-bits','dot-product'):
        ref=root/f'release-{n}';steps=read(root/f'oracle-{n}/report.json')['steps']
        columns=[len(c) for _,c in read(root/f'release-input-{n}/export-schema.json')['tables']]
        modes={}
        for label,p in [('baseline',f'study-{n}-0'),('table',f'fresh-1-{n}'),('shard',f'study-{n}-2'),('indexed_repair',f'repair-{n}'),('shard_without_prefix',f'filter-3-{n}'),('prefix',f'upper-{n}')]:
            path=folder/p;rr=read(path/'resident.json')
            info={'resident':rr,'median_ms':median(s['inference_ms'] for s in rr['samples'])}
            for k in ('base','detail'):
                if (path/k/'parents.bin').exists():info[k]=inspect_device(path/k,ref,steps,columns)
            info['audited_device_sha256']=check_mps(path,ref,columns)
            modes[label]=info
        for f,label in [(0,'baseline'),(2,'shard'),(4,'prefix')]:
            counter_path=folder/(f'count-prefix-{n}' if f==4 else f'work-{n}-{f}')
            d=read(counter_path/'run.json')
            check_mps(counter_path,ref,columns)
            assert d['finished'] and d['completed']==len(steps)
            modes[label]['work']=dict(zip(
                ['scheduled_workers','table_rejected_workers','shard_rejected_workers','dfs_iterations','repair_rows_examined'],
                d['state'][51:56],strict=True))
        checks={}
        for label,sub in [('baseline',f'study-{n}-0'),('table',f'fresh-1-{n}'),('shard',f'study-{n}-2'),('prefix',f'upper-{n}'),('release',f'final-{n}')]:
            d=read(folder/sub/'check.json');assert d['acceptance']=='pass'
            checks[label]={k:d[k] for k in ('acceptance','ordered_exact','full_typed_graph_equal','tokens','gpu_continuations')}
        cpu=read(folder/f'cpu-resident-{n}.json')
        refreport=read(root/f'oracle-{n}/report.json')
        assert cpu['program_sha256']==refreport['program_sha256'] and len(cpu['inference_ms'])==9
        cases[n]=dict(cold=cold[n],warm=warm[n],modes=modes,checks=checks,
                      cpu_resident_ms=cpu['inference_ms'],cpu_resident_median_ms=cpu['median_ms'],
                      cpu_repaired_dependencies=refreport['stats']['repaired_dependencies'],
                      system_trace=system_trace(folder,n,root/f'export-{n}',skill))
    out.mkdir(parents=True,exist_ok=True)
    (out/'profile.json').write_text(json.dumps(dict(cases=cases,isolation=read(folder/'final-isolation.json')),indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('directory','reference','skill','out'):p.add_argument(k,type=Path)
    a=p.parse_args();report(a.directory,a.reference,a.skill,a.out)
