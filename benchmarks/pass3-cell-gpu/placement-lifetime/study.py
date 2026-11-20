"""Measure a native physical decision stream on the archived source, without rebuilding the trial census."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'prospective-owner-placement'
ARMS=('pooled/keep','multi-prefix/keep','defer/keep','defer/retrained')
CASES=('gemm-bias-relu','gated-state')


def load(path):
    return json.loads(path.read_bytes())


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    f=a.out/(a.case+'.json')
    rows=load(f) if f.exists() else {}
    controls=load(PARENT/'stream.json')[a.case]
    with (PARENT/'actions.jsonl').open() as handle:
        keys=json.loads(next(handle))
        ledger=[dict(zip(keys,json.loads(line))) for line in handle]
    source=a.exp/'owner-action-fresh-v1'/a.case/'program.json'
    for arm in a.arms:
        if arm in rows:continue
        previous=controls[arm]
        layout,decision=arm.split('/')
        offers=[ledger[i] for i in previous['actions']]
        assert all(e['source']==a.case for e in offers)
        spec={'runs':previous['runs'],'offers':offers,'forced':decision=='merge'}
        if decision=='retrained':
            spec['weights']=load(PARENT/'natural-regression.json')
        with tempfile.TemporaryDirectory(dir=a.out) as tmp:
            tmp=Path(tmp);inputs=tmp/'input.json';inputs.write_text(json.dumps(spec))
            row={'program_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                 'opportunity_sha':sha(offers),'policy_sha':sha(spec.get('weights'))}
            for mode in ('audit','measure'):
                result=tmp/'result.json';start=perf_counter()
                subprocess.run([a.engine,source,inputs,layout,result,mode,str(a.stride)],check=True)
                v=load(result)
                assert (v['graph'],v['runs'],v['placement'])==(previous['graph'],previous['runs'],previous['placement'])
                assert (v['issued'],v['selected'],v['saved'])==(previous['issued'],previous['selected'],previous['immediate_bytes'])
                if mode=='audit':
                    assert sha(v['source'])==previous['source_sha']
                    row['source_sha']=sha(v['source'])
                else:
                    row.update({k:v[k] for k in ('probes','probe_ns','runs','graph','issued','selected','saved','placement','phase_bytes',
                                                'initial','base','static_start','static_end','after_export','terminal','program_fields','curve')})
                    assert row['curve'][-1][5]==previous['final_charge'][0]
                    assert row['curve'][-1][0]==row['runs'] and all(r[0]==n for n,r in enumerate(row['curve']))
                    assert row['after_export']==row['terminal'],(row['after_export'],row['terminal'])
                    if a.stride==1:
                        assert all(entry[1]>0 for entry in row['curve'])
                    row['stride']=a.stride
                    row['diagnostic_seconds']=perf_counter()-start
                print(a.case,arm,mode,round(perf_counter()-start,2),v['runs'],v['terminal'][0],flush=True)
            if decision=='retrained':
                # Reject corrupted intervention coordinates before issuing a storage move.
                negative={}
                for field,error in [('epoch','incorrect placement boundary'),('selected','native gate chose another action')]:
                    bad=load(inputs)
                    if field=='epoch':bad['offers'][0]['epoch']+=1
                    else:bad['offers'][0]['selected']=not bad['offers'][0]['selected']
                    corrupted=tmp/(field+'.json');corrupted.write_text(json.dumps(bad))
                    check=subprocess.run([a.engine,source,corrupted,layout,tmp/'rejected.json','audit','0'],
                                         text=True,capture_output=True)
                    assert check.returncode!=0 and error in check.stderr,(check.returncode,check.stderr)
                    negative[field]=True
                row['rejected']=negative
        rows[arm]=row
        partial=f.with_suffix('.tmp');partial.write_text(json.dumps(rows,separators=(',',':'))+'\n');partial.replace(f)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','engine','out'):p.add_argument(k,type=Path)
    p.add_argument('case',choices=CASES);p.add_argument('--arms',nargs='+',choices=ARMS,default=ARMS)
    p.add_argument('--stride',type=int,default=1)
    run(p.parse_args())
