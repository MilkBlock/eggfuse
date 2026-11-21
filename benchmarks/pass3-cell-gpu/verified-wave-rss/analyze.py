"""Compute first-passage times to independent CPU-calibrated, common RSS levels."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent


def first(trace,threshold):
    if trace[0][1]>=threshold:
        return {"status":"left","ms":0.0,"interval_ms":0.0,"physical":trace[0][2:]}
    for a,b in zip(trace,trace[1:]):
        if b[1]>=threshold:
            return {"status":"reached","ms":b[0]/1000,"interval_ms":(b[0]-a[0])/1000,"physical":b[2:]}
    return {"status":"unreached","ms":None}


def metrics(pair,levels):
    v=pair['sampled'];t=v['trace']
    assert len(t)>=5 and t[0][0]==0 and t[-1][0]==v['interval_us']
    assert all(x[0]<y[0] and all(a<=b for a,b in zip(x[2:],y[2:])) for x,y in zip(t,t[1:]))
    assert all(rss>0 and u+e<=g for _,rss,g,u,e in t)
    assert t[-1][2:]==v['counts']==pair['plain']['counts']
    begin=t[0][1];mx=max(x[1] for x in t);peak=next(r for r in t if r[1]==mx)
    return dict(start_mib=begin/1024,peak_mib=mx/1024,rise_mib=(mx-begin)/1024,end_mib=t[-1][1]/1024,
                own_peak_ms=peak[0]/1000,own_peak_physical=peak[2:],counts=v['counts'],sample_count=len(t),
                peak_gap_ms=max(b[0]-a[0] for a,b in zip(t,t[1:]))/1000,plain_ms=pair['plain']['ms'],
                sampled_ms=v['ms'],overhead_ms=v['ms']-pair['plain']['ms'],overhead_pct=100*(v['ms']/pair['plain']['ms']-1),
                thresholds={f'{kind}{frac}':first(t,(absolute if kind=='abs' else begin+delta))
                            for frac,(absolute,delta) in levels.items() for kind in ('abs','delta')})


def summarize(cases,evidence):
    info={}
    for case,raw in cases.items():
        gold=evidence[case]['reference']
        cal=raw['calibration'];assert len(cal)==3
        b=median(t['trace'][0][1] for t in cal)
        d=median(max(row[1] for row in t['trace'])-t['trace'][0][1] for t in cal)
        levels=raw['thresholds_kib']
        assert all(levels[str(f)]==[b+round(f*d),round(f*d)] for f in (.5,.9))
        info[case]=dict(calibration=[metrics({'sampled':r,'plain':r},levels)['rise_mib'] for r in cal],
                        calibrated_baseline_mib=b/1024,calibrated_rise_mib=d/1024,thresholds_kib=levels,arms={})
        for name,pairs in raw['rows'].items():
            assert len(pairs)==4
            for p in pairs:
                for r in p.values():
                    assert r['state_sha']==gold['state_sha'] and r['runs']==gold['runs']
            rows=[metrics(p,levels) for p in pairs]
            summary={k:median(r[k] for r in rows) for k in rows[0] if k not in ('thresholds','own_peak_physical','counts')}
            summary['counts']=rows[0]['counts']
            assert all(r['counts']==summary['counts'] for r in rows)
            summary['thresholds']={}
            for k in rows[0]['thresholds']:
                obs=[r['thresholds'][k] for r in rows]
                reached=[v for v in obs if v['status']=='reached']
                summary['thresholds'][k]=dict(outcomes=dict(Counter(v['status'] for v in obs)),
                    median_ms=median(v['ms'] for v in reached) if reached else None,
                    median_redeemed_at_cross=median(v['physical'][1] for v in reached) if reached else None)
            if name!='cpu':
                audit=evidence[case]['arms'][name]
                assert all(audit['checks'].values()) and audit['source']['state_sha']==gold['state_sha']
                st=audit['storage']
                assert summary['counts']==[st.get(k,0) for k in ('granted','used','unused')]
                if st:
                    assert st['used']==st['payload_identity'] and st['granted']==st['used']+st['unused']
            info[case]['arms'][name]={'median':summary,'runs':rows}
    return info


def main():
    p=argparse.ArgumentParser()
    for k in ('curves','audit','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    cases={k:json.loads((a.curves/(k+'.json')).read_bytes()) for k in ('sum-bits','3mm')}
    evidence={k:json.loads((a.audit/(k+'.json')).read_bytes()) for k in cases}
    summary=summarize(cases,evidence)
    a.out.mkdir(exist_ok=True)
    (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
    (a.out/'audit.json').write_text(json.dumps(evidence,indent=1)+'\n')
    # Lossless delta text; every external sample at the retained microsecond/KiB resolution.
    compressed={}
    for case,raw in cases.items():
        for v in [*raw['calibration'],*(r['sampled'] for pairs in raw['rows'].values() for r in pairs)]:
            trace=v.pop('trace')
            v['trace_deltas']=[trace[0]]+[[y-x for x,y in zip(a,b)] for a,b in zip(trace,trace[1:])]
        compressed[case]=raw
    (a.out/'curves.json').write_text(json.dumps(compressed,separators=(',',':'))+'\n')


if __name__=='__main__':main()
