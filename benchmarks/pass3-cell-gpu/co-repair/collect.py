"""Freeze the family split before collecting real co-repair and source Run labels."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

GPU = Path(__file__).resolve().parents[1]
REPO = GPU.parents[1]
DIVERSITY = REPO / 'benchmarks/eggcc-diversity'
sys.path.insert(0, str(GPU))
from events_audit import align
from endpoint import endpoint


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(*cmd):
    subprocess.run([str(x) for x in cmd], check=True, stdout=subprocess.DEVNULL)


def collect(case, args):
    name = case['name']
    anchor = case['split'] == 'anchor'
    folder = args.output / name
    if anchor:
        program = args.reference / name / 'program.json'
    else:
        source = args.inputs / (name+'.egg')
        proof = read(DIVERSITY/'validation.json')['cases'][name]['pass3']
        if digest(source) != proof['input_sha256']:
            raise ValueError(f'changed input: {name}')
        program = folder / 'program.json'
        if not program.exists():
            call(args.compiler, 'compile','--source',source,'--bake-source',
                 args.reference/'sum-bits/bake-source.egg','--output',folder)
        if digest(folder/'source.egg') != digest(source):
            raise ValueError(f'compiled a different source: {name}')
    folder.mkdir(parents=True,exist_ok=True)
    plain = args.reference/f'oracle-{name}' if anchor else folder/'reference'
    if not plain.exists():
        call(args.runtime,'--program',program,'--output',plain)
    detail = folder/'observation'
    if not detail.exists():
        call(args.runtime,'--program',program,'--output',detail,'--audit-repair-inputs')
    program_id = read(program)['sha256']
    cpu = read(plain/'report.json')
    observed = read(detail/'report.json')
    assert cpu['program_sha256'] == observed['program_sha256'] == program_id
    for key in ('rhs.json','writes.json','resumes.json','state.json'):
        assert digest(plain/key)==digest(detail/key),(name,key)
    step_fields=('ruleset','changed','path','iterations','executed_bindings')
    assert len(cpu['steps'])==len(observed['steps']) and all(
        all(a[k]==b[k] for k in step_fields) for a,b in zip(cpu['steps'],observed['steps']))
    events = read(detail/'events.json')
    assert len(events)==len(cpu['steps'])
    counts = {'unions':0,'subscribers':0,'key_checks':0,'collisions':0}
    for run in events:
        for i,event in enumerate(run):
            if event[0]=='displaced':
                assert run[i+1]==['union',*event[1:3]]
                counts['unions']+=1
                counts['subscribers']+=len(event[3])
            elif event[0]=='key-check':
                counts['key_checks']+=1
                counts['collisions']+=int(event[2] is not None)
    assert counts['unions']==cpu['stats']['unions']
    item=dict(name=name,family=case['family'],split=case['split'],runs=len(events),
              program=program_id,events_sha256=digest(detail/'events.json'),
              rhs=digest(plain/'rhs.json'),writes=digest(plain/'writes.json'),spine=digest(plain/'resumes.json'),
              graph=digest(plain/'state.json'),**counts)
    (folder/'cpu-check.json').write_text(json.dumps(item,indent=2)+'\n')
    image=args.reference/f'release-input-{name}' if anchor else folder/'input'
    device=args.reference/f'release-{name}' if anchor else folder/'device'
    if not image.exists():
        call(sys.executable,GPU/'codec.py',program,image)
        call(sys.executable,GPU/'lower.py',image/'ingress.json')
    if not device.exists():
        call(sys.executable,GPU/'run.py',image/'device.json',args.weights,device,'--port-weights',args.reference/'ports-1703.pt',
             '--runs',2048)
    ordered=align(program,image/'ingress.json',device,plain,detail,detail/'repair-inputs.json')
    path=folder/'ordered.json'
    path.write_text(json.dumps(ordered,separators=(',',':'))+'\n')
    accepted=endpoint(image/'ingress.json',device,plain,path)
    if accepted['acceptance']!='pass':
        raise ValueError((name,ordered['first_bad'],accepted))
    item['gpu_exact']=accepted['ordered_exact']
    return item


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('inputs','reference','weights','compiler','runtime','output'):
        parser.add_argument(field,type=lambda x:Path(x).resolve())
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cases=read(DIVERSITY/'manifest.json')['cases']+[
        dict(name=n,split='anchor',family=n) for n in ('sum-bits','dot-product')]
    results={}
    for case in cases:
        name=case['name']
        try:
            results[name]=collect(case,args)
            print(name,results[name]['runs'],results[name]['unions'],flush=True)
        except (ValueError,AssertionError,KeyError,OSError,subprocess.CalledProcessError) as exc:
            results[name]=dict(name=name,split=case['split'],error=str(exc))
            print(name,repr(exc),file=sys.stderr,flush=True)
        (args.output/'collection.json').write_text(json.dumps(results,indent=2)+'\n')
    if any('error' in item for item in results.values()):sys.exit(1)
