"""Generate a fresh MPS benchmark, Metal timestamp profiles, and independent Run audits."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
GPU=HERE.parent
REPO=GPU.parents[1]


def reproduce(root,address,out,skill):
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0')
    def run(*cmd,stdout=None):
        subprocess.run(list(map(str,cmd)),cwd=REPO,env=env,stdout=stdout,check=True)
    def py(script,*args):run(sys.executable,script,*args)
    run('xcrun','swiftc','-O',HERE/'encoders.swift','-o',out/'phases')
    cpu=Path(env.get('CARGO_TARGET_DIR',REPO/'target'))/'release'
    for package in ('eggfuse-cell-compiler','eggfuse-cell-runtime'):
        run('cargo','build','--release','--locked','-p',package)
    for n in ('sum-bits','dot-product'):
        image=root/f'release-input-{n}'/'device.json'
        # Unsplit production encoders for the pre-optimization configuration.
        trace=out/f'{n}.trace'
        run('xcrun','xctrace','record','--template','Metal System Trace','--no-prompt','--output',trace,'--launch','--',
            sys.executable,GPU/'run.py',image,address,out/f'xctrace-{n}','--port-weights',root/'ports-1703.pt','--freshness',0,'--export-only')
        run('xcrun','xctrace','export','--input',trace,'--toc','--output',out/f'{n}-toc.xml')
        run('xcrun','xctrace','export','--input',trace,'--xpath','/trace-toc/run[@number="1"]/data/table[@schema="metal-gpu-intervals"]',
            '--output',out/f'{n}-gpu.xml')
        with (out/f'cpu-resident-{n}.json').open('w') as f:
            run(cpu/'eggfuse-cell-compiler','bench','--program',root/n/'program.json','--repeat',9,stdout=f)
        for label,mode,stages,extra in [
                (f'study-{n}-0',0,('base','detail'),()),(f'fresh-1-{n}',1,(),()),
                (f'study-{n}-2',2,('base','detail'),()),(f'filter-3-{n}',3,(),()),
                (f'upper-{n}',4,('base','detail'),()),(f'repair-{n}',2,('detail',),('--index-repair',))]:
            folder=out/label
            py(HERE/'resident.py',root,address,folder,n,'--freshness',mode,*extra,*(['--capture'] if stages else []))
            for stage in stages:run(out/'phases',folder/'ingress',folder/stage,stage)
        for mode,dst in [(0,f'work-{n}-0'),(2,f'work-{n}-2'),(4,f'count-prefix-{n}')]:
            py(GPU/'run.py',image,address,out/dst,'--port-weights',root/'ports-1703.pt','--freshness',mode,'--count-work')
        py(GPU/'run.py',image,address,out/f'final-{n}','--port-weights',root/'ports-1703.pt')
        for label in [f'study-{n}-0',f'fresh-1-{n}',f'study-{n}-2',f'upper-{n}',f'final-{n}']:
            folder=out/label;packet=image.with_name('ingress.json');oracle=root/f'oracle-{n}'
            py(GPU/'events_audit.py',root/n/'program.json',packet,folder,oracle,root/f'events-lifecycle-{n}',folder/'ordered.json')
            py(GPU/'endpoint.py',packet,folder,oracle,folder/'check.json','--ordered',folder/'ordered.json')
    py(GPU/'isolated_check.py',root,address,out/'final-isolation.json')
    py(HERE/'warm_pair.py',root,address,out)
    py(HERE/'paired.py',root,out,address,cpu/'eggfuse-cell-runtime',out/'cold-final.json')
    py(HERE/'report.py',out,root,skill,out/'summary')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('verified_root','address_weights','new_output'):p.add_argument(k,type=Path)
    p.add_argument('--skill',type=Path,default=Path.home()/'.codex/skills/eggfuse-metal-profile')
    a=p.parse_args();reproduce(a.verified_root.resolve(),a.address_weights.resolve(),a.new_output.resolve(),a.skill)
