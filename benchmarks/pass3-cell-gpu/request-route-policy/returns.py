"""Compare deployed decisions to paired conditional timings on disjoint programs."""
import argparse,hashlib,json
from pathlib import Path
from statistics import median


def evaluate(events,arms):
    report={}
    for name,policies in arms.items():
        occurrences=[e for e in events if e['program']==name]
        contexts=[[e['run'],e['rule'],e['x']] for e in occurrences]
        key=hashlib.sha256(json.dumps(contexts,separators=(',',':')).encode()).hexdigest()
        benefit=[median(e['original_ns'])-median(e['request_ns']) for e in occurrences]
        possible=sum(max(0,d) for d in benefit)
        grouped={}
        for e,d in zip(occurrences,benefit):
            grouped.setdefault(tuple(e['x']),[]).append(d)
        feature_upper=sum(max(0,sum(g)) for g in grouped.values())
        mixed=sum(min(g)<0<max(g) for g in grouped.values())
        report[name]={'occurrences':len(contexts),'positive_calls':sum(v>0 for v in benefit),
                      'opportunity_us':possible/1000,'distinct_inputs':len(grouped),
                      'mixed_inputs':mixed,'best_by_input_us':feature_upper/1000,'policies':{}}
        for arm,r in policies.items():
            if arm in ('off','vanilla'):continue
            assert r['route_contexts']==key and len(r['route_actions'])==len(benefit)
            picked=[d for action,d in zip(r['route_actions'],benefit) if action=='1']
            captured=sum(max(0,d) for d in picked)
            penalty=-sum(min(0,d) for d in picked)
            report[name]['policies'][arm]=dict(wins=sum(d>0 for d in picked),picked=len(picked),
                  captured_us=captured/1000,penalty_us=penalty/1000,net_us=(captured-penalty)/1000,
                  gain_coverage=captured/possible if possible else None)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('events','arms','output'):p.add_argument(k,type=Path)
    a=p.parse_args()
    data=evaluate(json.loads(a.events.read_bytes()),json.loads(a.arms.read_bytes()))
    a.output.write_text(json.dumps(data,indent=1)+'\n')
