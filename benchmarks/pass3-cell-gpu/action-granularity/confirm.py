"""Check the production unit-id decoder on every source, against the complete timed study's actual winners."""
import argparse
import json
from pathlib import Path
from native_study import run,semantic,read


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    evidence={}
    for key,results in read(a.original/'results.json').items():
        case,seed=key.split('/')
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        observed={}
        for kind in ('raw','leaf','macro'):
            dest=a.out/f'{case}-{seed}-{kind}'
            run(a.runtime,program,dest,a.original/f'{case}-{seed}-plan.json',kind,audit=True)
            semantic(dest,a.original/f'{case}-reference')
            report=read(dest/'report.json')['action_units']
            previous=read(a.original/f'{case}-{seed}-{kind}'/'report.json')['action_units']
            assert report['issued']==previous['issued'] and report['provenance']==previous['provenance']
            assert report['raw_rejections']==previous['raw_rejections']
            observed[kind]=dict(roots=sum(bool(e[6]) for e in report['issued']),extensions=sum(bool(e[7]) for e in report['issued']),
                                same_source_ordinals=True,all_events_equal=True)
        evidence[key]=observed
    (a.out/'results.json').write_text(json.dumps(evidence,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('runtime','corpus','ref','original','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
