"""Controlled first-read interventions followed by matched native rollouts."""
import argparse
from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import torch
from first_reader import examples,fit
from policy import Pointer
from study import compile_case,rollout,exact,compare,semantic


def main(a):
    torch.set_num_threads(1)
    checkpoint=torch.load(a.checkpoint,map_location='cpu',weights_only=True)
    eval_banks=examples(torch.Generator().manual_seed(200800),4096,True,'productive')
    configs=[
        ('original',None),('local',(32,False,True,'productive',600)),
        ('short',(32,True,True,'productive',40)),
        ('sparse',(32,True,False,'productive',600)),
        ('any-left',(32,True,True,'any',600)),
        ('narrow',(8,True,True,'productive',600)),
        ('wide',(96,True,True,'productive',600)),
        ('context',(32,True,True,'productive',600)),
        ('diverse',(32,True,True,'productive',600,True)),
        ('shared',(0,True,True,'productive',600,True)),
    ]
    report={}
    with TemporaryDirectory() as tmp:
        root=Path(tmp); plans=root/'plans.json';plans.write_text('[]')
        cases=[]
        for i in range(48):
            kind=('absent','fresh','reuse')[i%3]
            path=compile_case(a.compiler,root,1810+i//3*11+i%3*5,kind)
            cases.append((path,exact(a.reference,path,plans)))
        for name,config in configs:
            results=[]
            for seed in ((1703,1709) if config else (1703,)):
                policy=Pointer().eval()
                policy.load_state_dict(checkpoint)
                if config:
                    policy.first_reader=fit(seed,*config)
                    if name=='shared':
                        torch.save(policy.state_dict(),a.out.with_name(f'shared-reader-{seed}.pt'))
                with torch.no_grad():
                    bank,labels=eval_banks
                    scores=(policy.first_reader(bank) if config else
                            policy.logits(bank,0,torch.zeros_like(bank[:,0])))
                    correct=labels.gather(1,scores.argmax(1,keepdim=True)).sum().item()
                metrics=Counter()
                for path,ref in cases:
                    out=rollout(a.native,path,policy,'learned')
                    checks=compare(out,ref)
                    metrics.update(ok=int(semantic(checks)),strict=int(all(checks.values())),
                                   **{k:out[k] for k in ('paid','pointer_scores','queries','receiver_reads','first_encoded','rejected','internal')})
                results.append(dict(seed=seed,first_correct=correct,model_parameters=sum(p.numel() for p in policy.parameters()),**metrics))
                print(name,results[-1],flush=True)
            report[name]=results
            a.out.write_text(json.dumps(dict(native_cases=len(cases),bank_cases=len(labels),arms=report),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('compiler','native','reference','checkpoint','out'):
        p.add_argument(arg,type=Path)
    main(p.parse_args())
