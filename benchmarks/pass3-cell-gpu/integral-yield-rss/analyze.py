"""Derive common RSS crossings and actual data-plane traffic at the last complete matched source Run."""
import argparse
from collections import Counter
from itertools import accumulate
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent


def crossed(trace,level):
    if trace[0][1]>=level:return 'left',trace[0],0
    for a,b in zip(trace,trace[1:]):
        if b[1]>=level:return 'reached',b,(b[0]-a[0])/1000
    return 'unreached',None,None


def progress(row,raw,filtered=None):
    run,actual,used,single,multi=row[2:]
    original=raw[run-1] if run else [0,0,0,0]
    out=dict(last_complete_run=run,wire_bytes=actual,wire_bytes_avoided=original[0]-actual,
                internally_committed=used,external_single=single,external_multi=multi,
                external_roots_avoided=original[2]+original[3]-single-multi)
    if filtered is not None:
        reference=filtered[run-1] if run else [0,0,0,0]
        out['additional_wire_avoided_vs_filter']=reference[0]-actual
        out['additional_roots_avoided_vs_filter']=reference[2]+reference[3]-single-multi
    return out


def median_cross(samples):
    good=[r for r in samples if r['status']=='reached']
    result={'outcomes':dict(Counter(r['status'] for r in samples))}
    if good:
        result.update({k:median(row[k] for row in good) for k in good[0] if k!='status'})
    return result


def summarize(data,evidence):
    result={}
    for case,raw in data.items():
        gold=evidence[case]['reference'];baseline=evidence[case]['arms']['raw_external']['ledger']['rows']
        assert len(baseline)==gold['runs']
        for name,a in evidence[case]['arms'].items():
            assert all(a['source']['checks'].values())
            for k in ('state_sha','rhs','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners'):
                assert a['source'][k]==evidence[case]['arms']['raw_external']['source'][k],(case,name,k)
            vals=a['ledger']['rows']
            for j,row in enumerate(vals):
                assert (row[0]<=baseline[j][0] and row[2]<=baseline[j][2] and row[3]==baseline[j][3]),(case,name,j)
        cal=raw['calibration'];b=median(x['trace'][0][1] for x in cal)
        gain=median(max(r[1] for r in x['trace'])-x['trace'][0][1] for x in cal)
        levels=raw['thresholds_kib']
        assert levels=={str(f):[b+round(f*gain),round(f*gain)] for f in (.5,.9)}
        assert len(cal)==3 and gain>0
        result[case]=dict(calibration_entry_mib=b/1024,calibration_growth_mib=gain/1024,thresholds_kib=levels,arms={})
        for name,pairs in raw['rows'].items():
            filtered=evidence[case]['arms']['filter_external']['ledger']['rows'] if name.startswith('filter_') else None
            trials=[]
            assert len(pairs)==4
            for item in pairs:
                v=item['sampled'];plain=item['plain']
                assert all(r[k]==gold[k] for r in (v,plain) for k in ('runs','state_sha'))
                tr=v['trace'];peak=max(r[1] for r in tr);pk=next(r for r in tr if r[1]==peak)
                assert all(x[0]<y[0] and x[2]<=y[2] for x,y in zip(tr,tr[1:]))
                if name!='cpu':
                    ledger=evidence[case]['arms'][name]['ledger']
                    assert ledger['digest']==v['ledger_hash'] and v['totals']==plain['totals']==ledger['rows'][-1]
                    assert all(r[3:]==(ledger['rows'][r[2]-1] if r[2] else [0]*4) for r in tr)
                z=dict(entry_mib=tr[0][1]/1024,peak_mib=peak/1024,rise_mib=(peak-tr[0][1])/1024,peak_ms=pk[0]/1000,
                       end_mib=tr[-1][1]/1024,plain_ms=plain['ms'],sampled_ms=v['ms'],overhead_pct=100*(v['ms']/plain['ms']-1),
                       samples=len(tr),max_gap_ms=max(y[0]-x[0] for x,y in zip(tr,tr[1:]))/1000,
                       end_progress=progress(tr[-1],baseline,filtered) if name!='cpu' else None,thresholds={})
                for frac,(absolute,delta) in levels.items():
                    for kind,level in [('abs',absolute),('delta',tr[0][1]+delta)]:
                        status,row,gap=crossed(tr,level)
                        obs={'status':status}
                        if row:
                            obs.update(ms=row[0]/1000,gap_ms=gap)
                            if name!='cpu':obs.update(progress(row,baseline,filtered))
                        z['thresholds'][kind+frac]=obs
                trials.append(z)
            summary={k:median(r[k] for r in trials) for k in trials[0] if k not in ('thresholds','end_progress')}
            summary['end_progress']=trials[0]['end_progress']
            summary['thresholds']={k:median_cross([r['thresholds'][k] for r in trials]) for k in trials[0]['thresholds']}
            result[case]['arms'][name]=dict(median=summary,trials=trials)
    return result


def delta(rows):
    return [rows[0],*[[y-x for x,y in zip(a,b)] for a,b in zip(rows,rows[1:])]]


def undelta(rows):
    return [list(row) for row in zip(*(accumulate(q) for q in zip(*rows)))]


def transform(cases,evidence,pack):
    adjust=delta if pack else undelta
    for raw in cases.values():
        for v in [*raw['calibration'],*(r['sampled'] for pairs in raw['rows'].values() for r in pairs)]:
            v['trace']=adjust(v['trace'])
    for case in evidence.values():
        for a in case['arms'].values():a['ledger']['rows']=adjust(a['ledger']['rows'])


def main():
    p=argparse.ArgumentParser()
    for k in ('curves','audit','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    read=lambda where:{name:json.loads((where/(name+'.json')).read_bytes()) for name in ('sum-bits','3mm')}
    data=read(a.curves);ev=read(a.audit);result=summarize(data,ev);transform(data,ev,True)
    (a.out/'curves.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    (a.out/'audit.json').write_text(json.dumps(ev,separators=(',',':'))+'\n')
    (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')


if __name__=='__main__':main()
