"""Fresh-process whole CLI including loading, one generation, source execution and device export."""
import argparse
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

# Keep the parent's clock outside worker imports and after-the-fact source audits.
def worker(args):
    import torch
    from study import Generation, specialize
    from policy import load_packet
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    plan=load_packet(args.plan,args.image)
    with torch.inference_mode():
        weights=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
        generator=Generation(plan,weights,args.device)
        specialize(plan,generator.emit,True,events=True)(args.image/'device.json',args.reader,args.ports,
                                                        2048,2,args.dest)


def main(a):
    from study import inputs,packet,verify
    from policy import save_packet
    report={}
    a.out.mkdir(parents=True,exist_ok=False)
    for case in ('sum-bits','dot-product'):
        image,program,gold=inputs(a.corpus,a.ref,case)
        static=a.out/f'{case}-plan.npz';save_packet(packet(image,program),static)
        for seed in (1703,1709):
            samples={'cpu':[],'mps':[]}
            for trial in range(4):
                for dev in (('cpu','mps') if trial%2==0 else ('mps','cpu')):
                    dest=a.out/f'{case}-{seed}-{trial}-{dev}'
                    cmd=[sys.executable,__file__,'worker',str(image),str(static),str(a.weights/f'policy-{seed}.pt'),
                         str(a.reader),str(a.ref/'ports-1703.pt'),str(dest),dev]
                    start=perf_counter_ns()
                    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
                    samples[dev].append((perf_counter_ns()-start)/1e6)
                    verify(dest,gold,image)
            report[f'{case}/{seed}']={n:dict(ms=v,median_ms=median(v),semantic_exact=True) for n,v in samples.items()}
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    w=sub.add_parser('worker');s=sub.add_parser('study')
    for k in ('image','plan','checkpoint','reader','ports','dest'):w.add_argument(k,type=Path)
    w.add_argument('device',choices=('cpu','mps'))
    for k in ('corpus','ref','reader','weights','out'):s.add_argument(k,type=Path)
    a=p.parse_args()
    if a.action=='worker':worker(a)
    else:main(a)
