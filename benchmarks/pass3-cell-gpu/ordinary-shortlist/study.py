"""Preserve exactly the same ordered neural proposals; alternate resident bindings backends."""
import argparse
from pathlib import Path
import json
import subprocess
import sys
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'ordinary-witness'))
from plan import sealed_plans
from trial import audit,command

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    arms={
        'native':(False,'off',0,None),
        'three':(False,'seal3xlearned',2,None),
        'sparse':(True,'sparseseal3xlearned',2,'three'),
        'epoch':(True,'epochseal3xlearned',2,'three'),
        'memo':(True,'memoseal3xlearned',2,'three'),
        'stack':(True,'stackseal3xlearned',2,'three'),
        'adaptive-one':(False,'sealadaptive',3,None),
        'stack-adaptive-one':(True,'stacksealadaptive',3,'adaptive-one'),
        'interval-three':(False,'seal3xcertified',2,None),
        'stack-interval-three':(True,'stackseal3xcertified',2,'interval-three'),
    }
    if a.flat:
        arms={'native':(False,'off',0,None),'three':(False,'seal3xlearned',2,None),
              'stack':(True,'stackseal3xlearned',2,'three'),'flat':(True,'flatseal3xlearned',2,'three'),
              'interval-three':(False,'seal3xcertified',2,None),'flat-interval-three':(True,'flatseal3xcertified',2,'interval-three')}
    summary={}
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        im=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        gold=a.ref/f'oracle-{case}' if anchor else a.corpus/case/'reference'
        plans=sealed_plans(im);pp=a.out/f'{case}-plans.json';pp.write_text(json.dumps(plans,separators=(',',':')))
        sessions={flag:subprocess.Popen([binary,program,pp,a.weights],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
                  for flag,binary in ((False,a.baseline),(True,a.overlay))}
        reports={};tickets={}
        try:
            for label,(fast,mode,radius,ref) in arms.items():
                r=command(sessions[fast],mode,radius,False,True,a.cap)
                validation=audit(r,im,gold,a.capture/case,a.corpus/case/'observation',plans)
                assert validation['exact'],(case,label,validation)
                x=r['report'];tickets[label]=x.pop('tickets')
                if ref:
                    assert x['raw_sha256']==reports[ref]['raw_sha256'] and x['counts']['raw_tuples']==reports[ref]['counts']['raw_tuples'],(case,label,'raw')
                    assert tickets[ref]==tickets[label] and x['neural_committed']==reports[ref]['neural_committed'],(case,label,'committed')
                reports[label]=dict(validation,**x,sha=r['state_sha'],ms=[],raw_and_winners_equal_to=ref)
            labels=list(arms)
            for repeat in range(a.repeats):
                order=labels[repeat%len(labels):]+labels[:repeat%len(labels)]
                for label in (order if repeat%2==0 else order[::-1]):
                    flag,mode,radius,_=arms[label]
                    r=command(sessions[flag],mode,radius,False,False,a.cap)
                    assert r['state_sha']==reports[label]['sha'] and r['report']['counts']==reports[label]['counts']
                    reports[label]['ms'].append(r['ms'])
            for label,v in reports.items():v['median_ms']=median(v['ms'])
        finally:
            for session in sessions.values():session.stdin.close();session.wait()
        summary[case]=reports
        (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],1),v.get('shortlist',{}).get('hits'),v['counts']['score_bucket_reads'])
                    for k,v in reports.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('baseline','overlay','weights','ref','corpus','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--repeats',type=int,default=10);p.add_argument('--cap',type=int,default=1000000)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--flat',action='store_true');main(p.parse_args())
