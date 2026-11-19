"""Time fresh executable processes, with the verified graph downloaded and written to disk."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def bench(root,address,cpu,out):
    lanes=('cpu','one','two','learned1703','learned1709');results={}
    for name in ('sum-bits','dot-product'):
        frozen={'one':root/f'release-one-{name}','two':root/f'release-{name}',
                **{f'learned{s}':root/f'release-{name}-learned-{s}' for s in (1703,1709)}}
        for folder in frozen.values():
            if read(folder/'check.json')['acceptance']!='pass':raise ValueError(f'unaccepted configuration: {folder}')
        if read(root/'native-gpu-sum/check.json')['status']!='pass' or read(root/'native-gpu-dot/check.json')['status']!='pass':
            raise ValueError('native final-state gate failed')
        refs={lane:sha((root/f'oracle-{name}' if lane=='cpu' else root/f'export-{name}')/'state.json') for lane in lanes}
        steps=read(root/f'oracle-{name}/report.json')['steps']
        case={lane:[] for lane in lanes}
        for j in range(4):
            order=lanes[j:]+lanes[:j]
            if name=='dot-product':order=order[::-1]
            for lane in order:
                with tempfile.TemporaryDirectory(dir=root) as tmp:
                    dest=Path(tmp)/'out'
                    if lane=='cpu':cmd=[cpu,'--program',root/name/'program.json','--output',dest]
                    else:
                        cmd=[sys.executable,HERE/'run.py',root/f'release-input-{name}'/'device.json',address,dest,
                             '--port-weights',root/'ports-1703.pt','--export-only','--lookup','hash','--arena','shared',
                             '--rows','1' if lane=='one' else '2','--tiles','64' if lane=='one' else '32']
                        if lane.startswith('learned'):cmd+=['--router',root/f'router-{lane[-4:]}.pt']
                    start=perf_counter_ns();subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
                    ms=(perf_counter_ns()-start)/1e6
                    if sha(dest/'state.json')!=refs[lane]:raise ValueError((name,lane,'export changed'))
                    if lane=='cpu':
                        r=read(dest/'report.json');infer=1000*r['inference_seconds']
                        assert len(r['steps'])==len(steps) and all(
                            all(a[k]==b[k] for k in ('ruleset','changed','executed_bindings')) for a,b in zip(r['steps'],steps))
                        assert not (dest/'rhs.json').exists(),'benchmark should use ordinary CPU build'
                    else:
                        r=read(dest/'run.json');infer=r['inference_ms'];assert r['finished'] and not r['fault']
                    if j:case[lane].append(dict(wall_ms=ms,inference_ms=infer))
            print(name,j,flush=True)
        results[name]={k:dict(samples=v,median_wall_ms=median(t['wall_ms'] for t in v),
                              median_inference_ms=median(t['inference_ms'] for t in v),
                              state_sha256=refs[k]) for k,v in case.items()}
    out.write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','address','cpu','out'):p.add_argument(k,type=Path)
    a=p.parse_args();bench(a.root,a.address,a.cpu.resolve(),a.out)
