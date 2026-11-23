"""Generate legal random programs; native effects provide labels and independent collision pairs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import subprocess


def program(seed, family, collision):
    rng = random.Random(seed)
    a,b,c,d,e = rng.sample(range(1, 1_000_000), 5)
    suffix = 'X' if seed % 2 else 'Y'
    name = 'Combine' + suffix
    outer = 'Envelope' + suffix
    expression = f'({name} old new)'
    extra_wants = ''
    if family == 'held_merge':
        expression = f'({outer} {expression})'
    elif family == 'held_result_pc':
        expression = f'({name} ({outer} old) new)'
        extra_wants = f'(Want ({outer} (Leaf {a})))\n(Want ({outer} (Leaf {b})))'
    seeds = [f'(Seed {x})' for x in (a,b,c)]
    rng.shuffle(seeds)
    # Both arms have the exact same table population before the collision rule
    # except for the endpoint of Connect (identity union in the control).
    source = f"""
(datatype K (Key i64))
(datatype E (Leaf i64) ({name} E E) ({outer} E) (Used E))
(function Read (K) E :merge {expression})
(relation Seed (i64))
(relation Connect (i64 i64))
(relation Want (E))
(ruleset install)
(ruleset collide)
(ruleset consume)
(rule ((Seed i)) ((set (Read (Key i)) (Leaf i)) ({name} (Leaf i) (Leaf {e}))) :ruleset install)
(rule ((Connect i j) (= a (Key i)) (= b (Key j))) ((union a b)) :ruleset collide)
(rule ((= z ({name} x y)) (Want x)) ((Used z)) :ruleset consume)
({name} (Leaf {d}) (Leaf {c}))
(Want (Leaf {d}))
(Want (Leaf {a}))
(Want (Leaf {b}))
{extra_wants}
{chr(10).join(seeds)}
(Connect {a} {b if collision else a})
(run-schedule (seq (run install) (run collide) (run consume)))
"""
    return source


def merge_family(p):
    # Replace each user constructor and each sort by a local symbol on first
    # appearance; preserve aliasing, instruction kind, operand wiring and result.
    def sig(merge):
        tables, sorts = {}, {}
        def sort(s):
            return (s['kind'], sorts.setdefault(s['name'],len(sorts)))
        def call(c):
            if 'table' in c:
                return ('construct',tables.setdefault(c['table'],len(tables)))
            return ('primitive',c['primitive'],c['inputs'],c['output'])
        return [merge['equal_inputs'], [sort(s) for s in merge['slots']],
                [(call(o['call']),o['args'],o['dst']) for o in merge['operations']],merge['result']]
    shapes = [sig(m) for m in p['merge_programs']['programs']
              if any('table' in o['call'] for o in m['operations'])]
    return hashlib.sha256(json.dumps(shapes,sort_keys=True).encode()).hexdigest()


def generate(compiler, receiver, root, count, holdouts, extra_family):
    if count < 4:
        raise ValueError('at least four training seeds required')
    if holdouts < 1:
        raise ValueError('empty holdout')
    splits = [('train',100,count),('held_program',100+count,holdouts),('held_merge',100+count+holdouts,holdouts)]
    if extra_family:
        splits.append(('held_result_pc',100+count+2*holdouts,holdouts))
    cases = [(split, seed, collision)
             for split, base, n in splits
             for seed in range(base,base+n) for collision in (False,True)]
    def one(case):
        split, seed, collision = case
        directory = root / f'{split}-{seed}-{int(collision)}'
        root.mkdir(parents=True,exist_ok=True)
        source = directory.with_suffix('.egg')
        source.write_text(program(seed,split,collision))
        subprocess.run([compiler,'compile','--source',source,'--output',directory],check=True,stdout=subprocess.DEVNULL)
        cmd = [receiver,'capture',directory/'program.json',directory/'tape.json','audit','--memory',directory/'memory.jsonl']
        report = json.loads(subprocess.check_output(cmd))
        if bool(report['runtime_events']) != collision:
            raise ValueError(f'{directory}: native execution disagreed with expected collision arm')
        p = json.loads((directory/'program.json').read_bytes())
        return dict(directory=directory.name,split=split,seed=seed,collision=collision,
                    merge_family=merge_family(p),state_sha=report['state_sha'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        manifest = list(pool.map(one,cases))
    for hold in ('held_program','held_merge'):
        if {r['seed'] for r in manifest if r['split']==hold} & {r['seed'] for r in manifest if r['split']=='train'}:
            raise ValueError('program leaked from train')
    families = lambda split: {r['merge_family'] for r in manifest if r['split']==split}
    if families('train') != families('held_program') or families('train') & families('held_merge'):
        raise ValueError('merge-template split leaked')
    if extra_family and families('held_result_pc') & (families('held_merge') | families('train')):
        raise ValueError('result PC holdout family leaked')
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('compiler',type=Path)
    ap.add_argument('receiver',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--count',type=int,default=8)
    ap.add_argument('--held-count',type=int,default=3)
    ap.add_argument('--extra-family',action='store_true')
    a=ap.parse_args()
    generate(a.compiler.resolve(),a.receiver.resolve(),a.output.resolve(),a.count,a.held_count,a.extra_family)
