"""Different entry forests for a bounded subset of actual eggcc tuple rules."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path


def forms(base, start, length):
    out = {f'(SubTuple {base} {start} {length})'}
    if length == 1:
        out.update((f'(Get {base} {start})', f'(Single (Get {base} {start}))'))
    else:
        # Only tuple-valued child forms; naked Get is a separate legitimate
        # entry when length one, not a replacement for a tuple child.
        for split in range(1, length):
            left = [f for f in forms(base,start,split) if not f.startswith('(Get ')]
            right = [f for f in forms(base,start+split,length-split) if not f.startswith('(Get ')]
            for a,b in itertools.product(left,right):out.add(f'(Concat {a} {b})')
    return sorted(out)


def main():
    p=argparse.ArgumentParser();p.add_argument('--program',type=Path)
    p.add_argument('--rules',type=Path,default=Path(__file__).with_name('source-rules.json'))
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    indices=[133,137,138,143,144]
    if args.program:
        program=json.loads(args.program.read_text())
        rules=[program['recipe']['rules'][i]['metadata']['name'] for i in indices]
        origin=dict(recipe_sha256=program['recipe']['sha256'],program_sha256=program['sha256'],
                    source_program_file_sha256=hashlib.sha256(args.program.read_bytes()).hexdigest())
    else:
        saved=json.loads(args.rules.read_text())
        assert [r['rule'] for r in saved['rules']]==indices
        rules=[r['source'] for r in saved['rules']]
        origin={k:saved[k] for k in ('recipe_sha256','program_sha256','source_program_file_sha256')}
    expected=['(rewrite (Concat (Concat','(rewrite (SubTuple expr x 1)',
              '(rewrite (SubTuple expr a b)', '(rule ((Get expr i))', '(rewrite (Concat (SubTuple']
    assert all(rule.startswith(prefix) for rule,prefix in zip(rules,expected)), 'recipe rule IDs changed'
    declarations='(datatype Expr (Input i64) (Get Expr i64) (Single Expr) (SubTuple Expr i64 i64) (Concat Expr Expr))\n(ruleset always-run)\n'
    common=declarations+'\n'.join(rules)+'\n'
    entries=set()
    # Different sizes, sharing and multiple roots; no output/target informs
    # this enumeration. Exact equal completion groups are discovered later.
    for base in ('(Input 0)',):
        for start in (0,1):
            for length in range(1,5):
                for f in forms(base,start,length):entries.add((f,))
    for bases in (('(Input 0)','(Input 0)'),('(Input 0)','(Input 1)')):
        for length1,length2 in ((1,1),(1,2),(2,2)):
            for start2 in (0,1,2):
                for a,b in itertools.product(forms(bases[0],0,length1),forms(bases[1],start2,length2)):
                    entries.add(tuple(sorted(set((a,b)))))
    cases=[]
    for roots in sorted(entries):
        key=hashlib.sha256(json.dumps(roots).encode()).hexdigest()[:16]
        # The runtime exporter appends two explicit verification Runs.
        source=common+'\n'.join(roots)+'\n(run-schedule (saturate (run always-run)))\n'
        cases.append(dict(id=key,metadata=dict(roots=roots),source=source,verify_ruleset='always-run',native_reference=True))
    result=dict(schema='eggfuse-real-multi-entry-input/v1',cases=cases,
                rules=[dict(rule=i,source=s) for i,s in zip(indices,rules)],
                **origin,
                scope='Generated entry forests; unmodified actual eggcc rules in a restricted positive ruleset. Not a production trace distribution.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print('cases',len(cases))


if __name__=='__main__':main()
