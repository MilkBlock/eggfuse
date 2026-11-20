"""Off-line static lowering for the CPU neural executor. No observed execution trace is an input."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from evaluate import HERE,read,sealed_plans


def prepare(a):
    if hashlib.sha256(a.program.read_bytes()).hexdigest()!=read(a.image/'ingress.json')['program_sha256']:
        raise ValueError('program and compiler input do not match')
    a.out.mkdir(parents=True,exist_ok=False)
    def write(name,data):(a.out/name).write_text(json.dumps(data,separators=(',',':'))+'\n')
    shutil.copyfile(a.program,a.out/'program.json');write('plans.json',sealed_plans(a.image))
    # Both models are frozen PyTorch exports. The online binary needs only these data and source program.
    single=read(HERE.parent/'single-witness'/f'{a.policy}-{a.seed}.json')
    single.update(residual=a.policy!='certified',mode='learned')
    write('single.json',single)
    shutil.copyfile(HERE.parent/'ordinary-witness'/f'weights-{a.seed}.json',a.out/'multi.json')
    gate=read(HERE/'weights'/f'nested-{a.seed}.json')
    write('merge.json',dict(program_sha256=read(a.program)['sha256'],weights=gate['weights'],control='learned'))
    write('root.json',dict(control='use',forbid_fallback=a.policy=='certified'))
    write('request.json',dict(source_sha256=hashlib.sha256(a.program.read_bytes()).hexdigest(),root_config='root.json',single_config='single.json',multi_weights='multi.json',merge_config='merge.json',
                              multi_mode='stackseal3xlearned',radius=2,cap=1000000,multi_residual=False,audit=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('program','image','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,choices=(1703,1709),default=1703)
    p.add_argument('--policy',choices=('high','certified'),default='certified')
    prepare(p.parse_args())
