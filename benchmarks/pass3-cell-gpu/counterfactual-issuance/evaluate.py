"""Freeze the signed-block actor and compare it against leaf, full and previous policy."""
import argparse
import json
from pathlib import Path
from train import block,study,work


def evaluate(a):
    weights=json.loads(a.checkpoint.read_bytes())['weights']
    report={}
    for case in a.cases:
        program,plans,req,spec=study['setup'](a,case)
        with study['src'].base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as run:
            exact=run({'audit':True})
        arms={}
        with study['src'].base.session(a.native,program,plans) as run:
            for name,mode,w in [('leaf','leaf',weights),('full','full',weights),
                                ('previous','greedy',block['weights']),('paired','greedy',weights)]:
                request=study['matrix']['cfg'](req,dict(spec,issuance_actor=dict(mode=mode,weights=w,seed=0),
                                            block_verifier=True,receipt_scan=2),True)
                data=run(request)
                counts,_=study['matrix']['summarize'](data,exact,True)
                arms[name]=dict(work(data),fept=counts['fept'],checks=counts['checks'],
                                token_actions=data['strict_named']['issuance_actor']['tokens'])
        report[case]=arms
        (a.out/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(case,arms,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('exp','native','checkpoint','out'):
        p.add_argument(arg,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    evaluate(p.parse_args())
