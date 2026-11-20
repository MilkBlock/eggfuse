"""Darwin fresh-process peak RSS for complete source generation with and without sealed page bounds."""
import argparse
import importlib.util
import json,re,subprocess,sys
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def run(a):
    if sys.platform!='darwin':raise RuntimeError('requires Darwin /usr/bin/time -l byte counters')
    a.out.mkdir(parents=True,exist_ok=False);evidence=base.read(a.evidence);results={}
    keys=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        b=(a.extra if case=='deriche' else a.exp/'compact-holdouts-20261121-v1')/(case+'-1703')
        p=b/'program.json';d=base.read(b/'request.json')
        for k in ('single_config','multi_weights','merge_config','root_config'):d[k]=str(b/d[k])
        root=a.out/(case+'-root.json');root.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='checked_slots')))
        tables=a.exp/'baked-port-packed-study-v1';d.update(multi_weights=str(tables/'sum-bits-1703-tied.json'),
             baked_codes=str(tables/'sum-bits-1703-tied.bin'),baked_row_index=False,packed_lookup=True,radius=0,root_config=str(root),
             early_guards='constants',multi_mode='rowdeltapairguardstackseallearned',multi_generation='complete',
             rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        d=base.query(d,'all',keys)
        width=8192 if case=='deriche' else 7
        requests={'complete':d,'paged':dict(d,multi_page_tuples=width),
                  'frozen':dict(d,multi_page_tuples=width,forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
                                atom_constraints=2,multi_mode='rowdeltapairguardstackseal2xlearned',
                                tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))}
        names=['vanilla',*requests];report={k:dict(rss=[],ms=[]) for k in names}
        for i in range(a.repeats):
            seq=names[i%len(names):]+names[:i%len(names)]
            for k in seq if i%2 else reversed(seq):
                cmd=[a.native,p,b/'plans.json'] if k!='vanilla' else [a.exp/'compact-vanilla-20261121/vanilla',p]
                proc=subprocess.run(['/usr/bin/time','-l',*cmd],text=True,input=json.dumps(requests.get(k,{}))+'\n',
                                    capture_output=True,check=True)
                out=json.loads(proc.stdout);rss=re.search(r'^\s*(\d+)\s+maximum resident set size\s*$',proc.stderr,re.M)
                assert rss and out['state_sha']==evidence[case]['complete']['state_sha'] and out['runs']==evidence[case]['vanilla']['runs']
                if k!='vanilla':assert out['root_recipe']['allocated']==evidence[case][k]['root_allocated']
                report[k]['rss'].append(int(rss.group(1)));report[k]['ms'].append(out['ms'])
        for v in report.values():v['median_rss']=median(v['rss']);v['median_ms']=median(v['ms'])
        results[case]=report;(a.out/'rss.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_rss']/2**20,1)) for k,v in report.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','extra','evidence','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','deriche']);p.add_argument('--repeats',type=int,default=3)
    run(p.parse_args())
