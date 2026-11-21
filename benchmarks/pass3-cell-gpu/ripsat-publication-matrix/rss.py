"""First passage at the common independently calibrated resident-memory levels on the typed ABI."""
import argparse,json,mmap,struct,subprocess,tempfile,threading
from pathlib import Path
from runpy import run_path
from statistics import median
from collections import Counter
HERE=Path(__file__).resolve().parent
main=run_path(str(HERE/'study.py'))
observer=run_path(str(HERE.parent/'verified-wave-rss/measure.py'))['observer']
cal_file=HERE.parent/'verified-wave-rss/results.json'

def one(native,program,plans,req,sample,want):
    with tempfile.TemporaryDirectory() as folder:
        file=Path(folder)/'window';file.write_bytes(bytes(4096))
        with file.open('r+b') as f,mmap.mmap(f.fileno(),4096) as mem:
            points=[];errors=[];done=threading.Event()
            with subprocess.Popen([native,program,plans],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as child:
                thread=None
                if sample:
                    req=dict(req,rss_file=str(file));thread=threading.Thread(target=observer,args=(child.pid,mem,done,points,errors));thread.start()
                try:
                    out,_=child.communicate((json.dumps(req)+'\n').encode())
                finally:
                    done.set()
                    if thread:thread.join()
                assert child.returncode==0,child.returncode
            v=json.loads(out);assert 'source_error' not in v,v.get('source_error')
            sn=v.get('strict_named') or {};counts=sn.get('counts',{})
            audit=dict(runs=v['runs'],state_sha=v['state_sha'],emitted=v['root_recipe']['emitted'],
                       internal=counts.get('source_commits',0),set_internal=sn.get('set_publication',{}).get('confirmed',0))
            assert all(audit[k]==want[k] for k in audit) and counts.get('audit_score_inputs',0)==0 and not sn.get('set_commits',[])
            r=dict(ms=v['ms'],endpoints=audit)
            if sample:
                assert not errors,errors
                start,r0,end,r1=struct.unpack_from('4Q',mem);assert start<end and r0>0 and r1>0
                assert abs((end-start)/1e6-v['ms']) < max(2,v['ms']*.01)
                t=[(start,r0),*((q[0],q[1]) for q in points if start<q[0]<end),(end,r1)]
                r['trace']=[[round((us-start)/1000),n//1024] for us,n in t];assert len(t)>=5
            return r

def crossing(t,level):
    if t[0][1]>=level:return ['left',0,0]
    for a,b in zip(t,t[1:]):
        if b[1]>=level:return ['reached',b[0],b[0]-a[0]]
    return ['unreached',None,None]

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);semantic=main['read'](a.study);cal=main['read'](cal_file);cases={}
    methods=main['METHODS']
    for case in ('sum-bits','3mm'):
        file,plan,req=main['src'].config(a,case);specs,lib=main['libraries'](a.exp,file,case);req['source_sha256']=lib['target_sha256']
        assert lib==semantic[case]['library'] and main['sha'](a.native)==semantic[case]['native_sha256']
        rows={n:[] for n in methods};order=[];levels=cal[case]['thresholds_kib']['0.9']
        for i in range(4):
            for j,n in enumerate(methods[i:]+methods[:i]):
                pair={}
                for sample in ((True,False) if (i+methods.index(n))%2==0 else (False,True)):
                    pair[sample]=one(a.native,file,plan,main['cfg'](req,specs[n]),sample,semantic[case]['arms'][n]);order.append([i,n,sample])
                t=pair[True]['trace'];base=t[0][1];peak=max(row[1] for row in t)
                assert pair[True]['endpoints']==pair[False]['endpoints']
                rows[n].append(dict(trace=t,samples=len(t),endpoints=pair[True]['endpoints'],entry_kib=base,peak_kib=peak,
                    rise_kib=peak-base,max_gap_us=max(b[0]-a[0] for a,b in zip(t,t[1:])),own_peak_us=next(us for us,rss in t if rss==peak),
                    abs_crossing=crossing(t,levels[0]),growth_crossing=crossing(t,base+levels[1]),
                    sampled_ms=pair[True]['ms'],plain_ms=pair[False]['ms'],overhead_pct=100*(pair[True]['ms']/pair[False]['ms']-1)))
            print(case,i+1,[(n,rows[n][-1]['growth_crossing']) for n in methods],flush=True)
        summary={}
        for n,trials in rows.items():
            z={k:median(t[k] for t in trials) for k in ('entry_kib','peak_kib','rise_kib','own_peak_us','sampled_ms','plain_ms','overhead_pct','samples','max_gap_us')}
            for key in ('abs_crossing','growth_crossing'):
                obs=[t[key] for t in trials];hits=[t[1] for t in obs if t[0]=='reached']
                z[key]=dict(outcomes=dict(Counter(t[0] for t in obs)),median_us=median(hits) if hits else None)
            summary[n]=z
        cases[case]=dict(calibration_sha256=main['sha'](cal_file),semantic_sha256=main['sha'](a.study),reference_levels_kib=levels,order=order,arms=rows,summary=summary)
        (a.out/'rss.json').write_text(json.dumps(cases,separators=(',',':'))+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','study','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
