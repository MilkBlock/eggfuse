"""Fresh-process inference-window RSS. Only the external observer stores samples."""
from argparse import ArgumentParser
from collections import defaultdict
import ctypes
import json
import mmap
from pathlib import Path
from runpy import run_path
from statistics import median
import struct
import subprocess
from tempfile import TemporaryDirectory
import threading
import time

HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'verified-wave-execution/study.py'))
source=base['source']
ARMS=('cpu','raw','filter','packed','ports','fraction','coverage')
KEYS=('rhs','commits','raw','multi','physical','cells','state_sha','root_parents','root_ids','nested_ids','children','single_winners','multi_winners')
PROC=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
PROC.proc_pidinfo.argtypes=(ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int)
PROC.proc_pidinfo.restype=ctypes.c_int
BUFF=(ctypes.c_uint64*12)
CLOCK=time.CLOCK_UPTIME_RAW


def observer(pid,mem,done,records,errors):
    buf=BUFF()
    try:
        while not done.is_set():
            start,end=struct.unpack_from('Q8xQ',mem)
            if end:break
            if start:
                ts=time.clock_gettime_ns(CLOCK)
                if PROC.proc_pidinfo(pid,4,0,buf,96)!=96:
                    if struct.unpack_from('Q',mem,16)[0]:break
                    raise OSError(ctypes.get_errno(),'proc_pidinfo')
                counts=struct.unpack_from('3Q',mem,32)
                records.append((ts,buf[1],*counts))
            time.sleep(.001)
    except Exception as e:
        errors.append(repr(e))


def run(binary,files,req,sampled):
    with TemporaryDirectory() as tmp:
        f=Path(tmp)/'window'
        f.write_bytes(bytes(4096))
        with f.open('r+b') as file,mmap.mmap(file.fileno(),4096) as mem:
            records=[];errors=[];done=threading.Event()
            if sampled:req=dict(req,rss_file=str(f))
            with subprocess.Popen([binary,*files],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
                thread=None
                if sampled:
                    thread=threading.Thread(target=observer,args=(proc.pid,mem,done,records,errors))
                    thread.start()
                try:
                    out,_=proc.communicate((json.dumps(req)+'\n').encode())
                finally:
                    done.set()
                    if thread:thread.join()
                if proc.returncode!=0:raise RuntimeError((binary,proc.returncode))
            v=json.loads(out)
            assert 'source_error' not in v,v.get('source_error')
            row={'ms':v['ms'],'runs':v['runs'],'state_sha':v['state_sha']}
            c=(v.get('spec_cells') or {}).get('counts',{})
            totals=[c.get(k,0) for k in ('granted','used','unused')]
            row['counts']=totals
            if sampled:
                assert not errors,errors
                start,before,end,after,*final=struct.unpack_from('7Q',mem)
                assert start<end and before and after and final==totals,(start,before,end,after,final,totals)
                ns=end-start
                assert abs(ns/1e6-v['ms'])<max(2,v['ms']*.01),(ns/1e6,v['ms'])
                samples=[(start,before,0,0,0),*(s for s in records if start<s[0]<end),(end,after,*final)]
                assert len(samples)>=5
                row['trace']=[[round((t-start)/1000),rss//1024,g,u,e] for t,rss,g,u,e in samples]
                row['interval_us']=round(ns/1000)
            return row


def configuration(a,case):
    p,plan,req=source.common.config(a,case);cfg=base['settings'](req,a)
    shared=cfg['pool']
    coverage=dict(shared,spec_cells=dict(shared['spec_cells'],wave_demand=dict(mode='count',weights=a.coverage)))
    arms={'cpu':{},'raw':cfg['off'],'filter':cfg['filter'],'packed':cfg['packed'],'ports':cfg['ports'],
          'fraction':shared,'coverage':coverage}
    return p,plan,arms


def audit(a,case,p,plan,arms):
    with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as reference:
        gold=reference({'audit':True})
    reports={}
    with source.base.session(a.build/'session',p,plan) as candidate:
        for name in ARMS[1:]:
            v=candidate(dict(arms[name],audit=True))
            q=source.base.summarize(v,gold)
            assert q['aligned'] and all(q['checks'].values())
            reports[name]=dict(checks=q['checks'],source={k:q[k] for k in KEYS},
                               storage=(v.get('spec_cells') or {}).get('counts',{}))
    return {'reference':{'state_sha':gold['state_sha'],'runs':gold['runs'],'rhs':gold['rhs_count']},'arms':reports}


def main():
    args=ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):args.add_argument(k,type=Path)
    args.add_argument('--audit',action='store_true')
    a=args.parse_args();a.seed=1703;a.cap=8192
    a.out.mkdir(parents=True,exist_ok=False)
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    heads=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']
    a.fraction=heads['fraction'];a.coverage=heads['coverage']
    for case in ('sum-bits','3mm'):
        p,plan,arms=configuration(a,case)
        if a.audit:
            v=audit(a,case,p,plan,arms)
            (a.out/(case+'.json')).write_text(json.dumps(v,indent=1)+'\n')
            print(case,'source verified',flush=True)
            continue
        def execute(name,sampled):
            return run(a.build/('vanilla' if name=='cpu' else 'session'),[p] if name=='cpu' else [p,plan],arms[name],sampled)
        calibration=[execute('cpu',True) for _ in range(3)]
        baselines=[r['trace'][0][1] for r in calibration]
        rises=[max(x[1] for x in r['trace'])-r['trace'][0][1] for r in calibration]
        assert min(rises)>0
        # Thresholds are committed to the output before measuring experimental arms.
        base_kib=int(median(baselines));gain_kib=int(median(rises))
        levels={str(frac):[base_kib+round(frac*gain_kib),round(frac*gain_kib)] for frac in (.5,.9)}
        out={'calibration':calibration,'thresholds_kib':levels,'rows':defaultdict(list),'order':[]}
        path=a.out/(case+'.json')
        path.write_text(json.dumps(out,separators=(',',':'))+'\n')
        for trial in range(4):
            start=(trial*2)%len(ARMS)
            seq=list(ARMS[start:]+ARMS[:start])
            if trial%2:seq.reverse()
            for index,name in enumerate(seq):
                # Alternate which member of a fresh sampled/unsampled pair goes first for each arm.
                flags=(True,False) if (trial+ARMS.index(name))%2==0 else (False,True)
                pair={}
                for f in flags:
                    obs=execute(name,f)
                    assert all(obs[k]==calibration[0][k] for k in ('runs','state_sha')),(case,name)
                    pair['sampled' if f else 'plain']=obs
                    out['order'].append([trial,name,f])
                out['rows'][name].append(pair)
            path.write_text(json.dumps(out,separators=(',',':'))+'\n')
            print(case,trial+1,[(k,round(z[-1]['sampled']['ms'],1)) for k,z in out['rows'].items()],flush=True)


if __name__=='__main__':main()
