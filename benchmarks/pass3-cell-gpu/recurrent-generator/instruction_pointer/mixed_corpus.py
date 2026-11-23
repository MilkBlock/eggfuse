"""Seal random captures and independent native EggCC captures into one split manifest."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_bytes())


def build(root,binary,training,held):
    if not training or not held or set(training)&set(held):
        raise ValueError('EggCC needs independent training and held programs')
    manifest=[]
    identities={}
    counts={}
    def register(directory,record):
        # Use source program identity, independent of optional compiler metadata.
        program=read(directory/'program.json')
        digest=hashlib.sha256(json.dumps(program['initial'],sort_keys=True).encode()+
                              json.dumps(program['source_core'],sort_keys=True).encode()).hexdigest()
        if digest in identities and identities[digest]!=record['split']:
            raise ValueError('duplicate program in two splits')
        identities[digest]=record['split']
        tape=read(directory/'tape.json')
        if tape['program_sha256']!=hashlib.sha256((directory/'program.json').read_bytes()).hexdigest():
            raise ValueError('teacher/program mismatch')
        histogram=Counter(r['run'] for r in tape['requests'])
        event_ids={e['token'] for e in tape['repair_events']}
        uses={r['run'] for r in tape['requests'] if any(p['address']['token'] in event_ids for p in r['parents'])}
        with (directory/'memory.jsonl').open() as lines:
            runs=sum(1 for _ in lines)
        group=counts.setdefault((record['split'],record['origin']),Counter())
        group.update(programs=1,runs=runs,actions=sum(histogram.values()),repair_input_runs=len(uses))
        manifest.append({**record,'directory':str(directory.relative_to(root)),
                         'runs':runs,'busy_runs':sorted(histogram),'repair_input_runs':sorted(uses)})
    for record in read(root/'random/manifest.json'):
        register(root/'random'/record['directory'],{**record,'origin':'random'})
    for split,names in [('train',training),('held_eggcc',held)]:
        for name in names:
            d=root/name
            capture=read(d/'capture.json')
            for role in ('reference','replay'):
                result=json.loads(subprocess.check_output([binary,role,d/'program.json',d/'tape.json','audit']))
                for key in ('state_sha','schedule','rhs','writes','resumes','events'):
                    if result[key]!=capture[key]:
                        raise ValueError(f'{name} {role} {key} differs')
                if role=='replay' and (result['unused'] or result['counts']['accepted']!=capture['matches']
                        or result['counts']['duplicates'] or result['counts']['rejected']):
                    raise ValueError('incomplete native label tape')
            register(d,dict(split=split,origin='eggcc',workload=name,seed=len(manifest),state_sha=capture['state_sha']))
    (root/'manifest.json').write_text(json.dumps(manifest)+'\n')
    print(json.dumps({f'{split}/{origin}':v for (split,origin),v in counts.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('binary',type=Path)
    p.add_argument('--training',nargs='+',required=True)
    p.add_argument('--held',nargs='+',required=True)
    a=p.parse_args()
    build(a.root.resolve(),a.binary.resolve(),a.training,a.held)
