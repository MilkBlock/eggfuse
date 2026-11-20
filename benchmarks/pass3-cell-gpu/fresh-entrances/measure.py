"""Test version-selected parent order with the same tied checkpoint and resident allocator."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'compact-recipes'))
from study import compare, read, session


def trial(case, seed, args):
    tag = f'{case}-{seed}'
    bundle = args.bundles / tag
    program = bundle / 'program.json'
    req = read(bundle / 'request.json')
    assert req['source_sha256'] == hashlib.sha256(program.read_bytes()).hexdigest()
    for key in ('single_config', 'merge_config'):
        req[key] = str(bundle / req[key])
    path = args.out / f'{tag}-root.json'
    path.write_text(json.dumps(dict(read(bundle / 'root.json'), encoding='resident')))
    req.update(root_config=str(path), multi_weights=str(args.tables / f'{tag}-tied.json'),
               baked_codes=str(args.tables / f'{tag}-tied.bin'), packed_lookup=True,
               multi_mode='stackseallearned', radius=0)
    with session(args.vanilla / 'vanilla-audit', program) as gold_run:
        gold = gold_run({'audit': True})
    with ExitStack() as stack:
        infer = stack.enter_context(session(args.native, program, bundle / 'plans.json'))
        vanilla = stack.enter_context(session(args.vanilla / 'vanilla', program))
        requests = {}
        result = {'vanilla': {'ms': [], 'rhs': gold['rhs_count']}}
        for arm in ('legacy', 'shared', 'same_width', 'plus_one'):
            request = req if arm == 'legacy' else dict(req, entrance=arm)
            output = infer(dict(request, audit=True))
            v = compare(output, gold)
            result[arm] = v
            if not v['aligned']:
                continue
            v['entrance'] = output['multi']['fresh_entrance']
            v['work'] = output['multi']['counts']
            if arm == 'shared':
                for f in ('raw', 'commits', 'physical', 'multi', 'children', 'cells'):
                    assert v[f] == result['legacy'][f], (tag, arm, f)
            assert v['rhs'] == v['neural_rhs'] == gold['rhs_count']
            assert v['direct_cells'] * 100 >= 98 * v['fresh']
            v['ms'] = []
            requests[arm] = request
        names = ['vanilla', *requests]
        for lap in range(1 + 2 * len(names)):
            pos = lap % len(names)
            order = names[pos:] + names[:pos]
            for arm in order if lap % 2 else reversed(order):
                timed = vanilla({}) if arm == 'vanilla' else infer(dict(requests[arm], audit=False))
                assert timed['state_sha'] == gold['state_sha'] and timed['runs'] == gold['runs']
                if arm != 'vanilla':
                    assert timed['root_recipe']['allocated'] == result[arm]['root_allocated']
                if lap:
                    result[arm]['ms'].append(timed['ms'])
        for arm in names:
            result[arm]['median_ms'] = median(result[arm]['ms'])
    print(tag, {k: v.get('median_ms', v.get('error', 'diverged')) for k, v in result.items()}, flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('native', 'vanilla', 'bundles', 'tables', 'out'):
        p.add_argument(name, type=Path)
    p.add_argument('--cases', nargs='+', default=['sum-bits', 'dot-product', 'jacobi-1d'])
    p.add_argument('--seeds', nargs='+', type=int, default=[1703])
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    study = {}
    for case in args.cases:
        for seed in args.seeds:
            study[f'{case}/{seed}'] = trial(case, seed, args)
            (args.out / 'results.json').write_text(json.dumps(study, indent=1) + '\n')
