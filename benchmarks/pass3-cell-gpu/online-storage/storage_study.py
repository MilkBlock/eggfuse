"""Same exact source-admission tuples and frozen layout library, three real native storage representations."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from statistics import median

def read(p):return json.loads(p.read_bytes())
def launch(*a):
    proc=subprocess.run(list(map(str,a)),capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stderr[-4096:]+proc.stdout[-2048:])
def main(a):
    a.out.mkdir(parents=True,exist_ok=a.resume);results={}
    driver=a.legacy/'target/release/examples/online_storage_trial';memory=a.legacy/'target/release/examples/runtime_storage_peak'
    for name in a.cases:
        case=a.out/name;case.mkdir(exist_ok=a.resume)
        program=a.ref/name/'program.json';library=a.legacy/f'library-{name}'/'library.json'
        phase=(library.parent/'phases').read_text().strip()
        modes={'dynamic':1,'leaf':2,'composed':3}
        current=None
        for attempt in range(12):
            groups=[]
            for mode,code in modes.items():
                dest=case/f'calibration-{attempt}-{mode}'
                if not (a.resume and (dest/'result.json').is_file()):launch(driver,program,dest,'calibrate',library,code,'all' if current is None else case/'mask.json')
                admissions=read(dest/'result.json')['admissions'];assert len({x[1] for x in admissions})==len(admissions)
                groups.append({tuple(x) for x in admissions})
            same=set.intersection(*groups)
            mask=sorted(x[1] for x in same)
            if all(g==same for g in groups):break
            if current==mask:raise ValueError('unequal exact admissions at fixed mask')
            current=mask;(case/'mask.json').write_text(json.dumps(mask))
        else:raise ValueError('admission intersection did not stabilize')
        assert len(mask)>0
        (case/'mask.json').write_text(json.dumps(mask))
        info={};truth=None;common=None
        for mode,code in modes.items():
            dest=case/f'audit-{mode}';
            if not (a.resume and (dest/'result.json').is_file()):launch(driver,program,dest,'audit',library,code,case/'mask.json')
            r=read(dest/'result.json')
            if truth is None:truth=r['stage_checks'];common=sorted(r['admissions'])
            else:assert truth==r['stage_checks'] and common==sorted(r['admissions'])
            assert len(common)==len(mask)
            data=case/f'memory-{mode}.json';state=case/f'state-{mode}.json'
            if not (a.resume and data.is_file() and state.is_file()):launch(memory,program,data,'inherited-owners','--port-domains-only','--cell-fields','--retired-prefixes',
                   '--integral',f'primary:{phase}','--integral-member-views','--integral-neighbors','--integral-library',library,
                   '--matched-storage',code,case/'mask.json','--state-output',state)
            m=read(data);assert m['final_state_sha256']==r['graph']
            info[mode]=dict(runs=r['runs'],admissions=len(common),physical=r['physical'],view_checks=dict(maximum_resolved_old_fact_refs=max(v[2] for v in r['view_checks']),
                peak_multi_run_instances=max(v[1] for v in r['view_checks']),final_members=r['view_checks'][-1]),graph=r['graph'],
                composition=r['integral']['composition'],storage=r['integral']['storage'],
                samples_ms=[],memory={k:v for k,v in m.items() if any(s in k for s in ('peak','teardown','live_after','cumulative_request')) and not isinstance(v,(dict,list))})
            info[mode]['curves']=[dict(run=s['run'],heap=s['after'],rss=s['rss_after'],records=s['physical_records']) for s in m['samples']]
        for trial in range(6):
            order=list(modes);order=order[trial%3:]+order[:trial%3]
            for mode in order if trial<3 else order[::-1]:
                dest=case/f'timing-{trial}-{mode}';
                if not (a.resume and (dest/'result.json').is_file()):launch(driver,program,dest,'timing',library,modes[mode],case/'mask.json')
                r=read(dest/'result.json');assert r['graph']==info[mode]['graph'] and r['physical']==info[mode]['physical']
                info[mode]['samples_ms'].append(r['inference_ms'])
        for v in info.values():v['median_ms']=median(v['samples_ms'])
        results[name]=dict(library_bytes=library.stat().st_size,catalog_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                           exact_admissions=len(mask),semantic_runs=len(truth),library_units=len(read(library)['edges']),arms=info)
        (a.out/'results.json').write_text(json.dumps(results,separators=(',',':'))+'\n')
        print(name,len(mask),[(k,v['physical']['integral_instances'],v['composition']['layout_switches'],round(v['median_ms'])) for k,v in info.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('legacy','ref','out'):p.add_argument(k,type=Path)
    p.add_argument('--resume',action='store_true');p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product']);main(p.parse_args())
