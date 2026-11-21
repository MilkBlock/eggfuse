"""Measure OS RSS alongside cumulative traffic at matched original source Runs."""
import argparse
import json
import mmap
from pathlib import Path
from runpy import run_path
from statistics import median
import struct
import subprocess
import tempfile
import threading
import time
import sys

HERE=Path(__file__).resolve().parent
prior=run_path(str(HERE.parent/'verified-wave-rss/measure.py'))
PROC=prior['PROC'];BUFF=prior['BUFF'];CLOCK=prior['CLOCK']
CASES=('sum-bits','3mm')
DEFAULT=('raw_external','filter_external','raw_closed','filter_closed','filter_mixed')


def read_point(m):
    # Snapshot produced by the target. Run acceptance rechecks *every* row
    # against the separate complete ordered audit of the same source execution.
    while True:
        seq,=struct.unpack_from('Q',m,64)
        if seq%2:continue
        run,wire,used=struct.unpack_from('3Q',m,32)
        single,multi=struct.unpack_from('2Q',m,72)
        if struct.unpack_from('Q',m,64)[0]==seq and run*2==seq:
            return [run,wire,used,single,multi]


def watch(pid,mem,done,points,errors):
    buf=BUFF()
    try:
        while not done.is_set():
            start,stop=struct.unpack_from('Q8xQ',mem)
            if stop:break
            if start:
                ts=time.clock_gettime_ns(CLOCK)
                if PROC.proc_pidinfo(pid,4,0,buf,96)!=96:
                    if struct.unpack_from('Q',mem,16)[0]:break
                    raise OSError('proc_pidinfo failed while inference was active')
                points.append([ts,buf[1],*read_point(mem)])
            time.sleep(.001)
    except Exception as e:
        errors.append(str(e))


def execute(binary,files,request,sampled,neural):
    if not neural:
        v=prior['run'](binary,files,request,sampled)
        if sampled:v['trace']=[q[:2]+[0]*5 for q in v['trace']]
        return v
    with tempfile.TemporaryDirectory() as t:
        page=Path(t)/'page';page.write_bytes(bytes(4096))
        with page.open('r+b') as f,mmap.mmap(f.fileno(),4096) as m:
            points=[];errors=[];done=threading.Event()
            if sampled:request=dict(request,rss_file=str(page))
            with subprocess.Popen([binary,*files],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as p:
                waiter=None
                if sampled:
                    waiter=threading.Thread(target=watch,args=(p.pid,m,done,points,errors));waiter.start()
                try:
                    out,_=p.communicate((json.dumps(request)+'\n').encode())
                finally:
                    done.set()
                    if waiter:waiter.join()
                assert p.returncode==0,p.returncode
            v=json.loads(out);assert 'source_error' not in v,v.get('source_error')
            root=v['root_recipe'];s=(v.get('integral_packets') or {}).get('counts',{})
            totals=[root['wire_bytes'],s.get('confirmed',0),*root['emitted']]
            r=dict(ms=v['ms'],runs=v['runs'],state_sha=v['state_sha'],totals=totals)
            if sampled:
                assert not errors,errors
                t0,r0,t1,r1=struct.unpack_from('4Q',m)
                end=read_point(m)
                assert t0<t1 and end==[r['runs'],*totals],(end,r)
                assert abs((t1-t0)/1e6-v['ms'])<max(2,v['ms']*.01)
                r['ledger_hash']=v['rss_runs']['digest']
                pts=[[t0,r0,0,0,0,0,0],*(pt for pt in points if t0<pt[0]<t1),[t1,r1,*end]]
                assert len(pts)>=5
                r['trace']=[[round((t-t0)/1000),rss//1024,*values] for t,rss,*values in pts]
            return r


def write(path,obj):
    path.write_text(json.dumps(obj,separators=(',',':'))+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('exp','build','out'):p.add_argument(field,type=Path)
    p.add_argument('--modes',nargs='+',default=list(DEFAULT));p.add_argument('--audit',action='store_true')
    a=p.parse_args();a.seed=1703
    a.out.mkdir(parents=True,exist_ok=False)
    joint=run_path(str(HERE.parent/'integral-filter-joint/study.py'))
    source=run_path(str(HERE.parent/'pair-source-frontier/profile.py'))
    for case in CASES:
        file,plan,req=source['config'](a,case)
        modes=['cpu',*a.modes]
        configs={k:joint['settings'](req,k) for k in a.modes};configs['cpu']={}
        if a.audit:
            with source['base'].session(a.exp/'compact-vanilla-20261121/vanilla-audit',file) as old:gold=old({'audit':True})
            rows=dict(reference={k:gold[k] for k in ('state_sha','runs','rhs_count')},arms={})
            with source['base'].session(a.build/'session',file,plan) as infer:
                for k,cfg in configs.items():
                    if k=='cpu':continue
                    v=infer(dict(cfg,audit=True,rss_ledger=True,birth_ledger=False))
                    assert 'source_error' not in v,v.get('source_error')
                    q=source['base'].summarize(v,gold);assert q['aligned'] and all(q['checks'].values())
                    led=v['rss_runs'];root=v['root_recipe']
                    assert len(led['rows'])==v['runs']==led['completed']
                    ip=(v.get('integral_packets') or {}).get('counts',{})
                    assert led['rows'][-1]==[root['wire_bytes'],ip.get('confirmed',0),*root['emitted']]
                    rows['arms'][k]=dict(ledger=led,source={x:q[x] for x in ('checks','state_sha','rhs','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners')})
            write(a.out/(case+'.json'),rows)
            print(case,'verified source and wire ledgers',flush=True);continue
        def one(mode,sampled):
            return execute(a.build/('vanilla' if mode=='cpu' else 'session'),[file] if mode=='cpu' else [file,plan],configs[mode],sampled,mode!='cpu')
        calibration=[one('cpu',True) for _ in range(3)]
        base=median(v['trace'][0][1] for v in calibration)
        rise=median(max(r[1] for r in v['trace'])-v['trace'][0][1] for v in calibration)
        assert rise>0
        levels={str(f):[int(base)+round(f*rise),round(f*rise)] for f in (.5,.9)}
        result={'calibration':calibration,'thresholds_kib':levels,'order':[],'rows':{k:[] for k in modes}}
        path=a.out/(case+'.json');write(path,result)
        for trial in range(4):
            start=(trial*2)%len(modes)
            order=modes[start:]+modes[:start]
            if trial%2:order.reverse()
            for k in order:
                pair={}
                for f in ([True,False] if (trial+modes.index(k))%2==0 else [False,True]):
                    v=one(k,f)
                    assert all(v[j]==calibration[0][j] for j in ('state_sha','runs'))
                    pair['sampled' if f else 'plain']=v;result['order'].append([trial,k,f])
                result['rows'][k].append(pair)
            write(path,result)
            print(case,trial+1,[round(result['rows'][k][-1]['sampled']['ms'],1) for k in modes],flush=True)


if __name__=='__main__':main()
