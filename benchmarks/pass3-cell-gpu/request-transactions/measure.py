"""Full Pass 3 comparison with identical issued parents and a fixed typed request library."""
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

ARMS = {
    'immediate': {'request_batch': 0},
    'transaction-1': {'request_batch': 1},
    'transaction-8': {'request_batch': 8},
    'shared-8': {'request_batch': 8, 'share_requests': True},
    'parents-8': {'request_batch': 8, 'share_requests': True, 'share_parents': True},
    'parents-32': {'request_batch': 32, 'share_requests': True, 'share_parents': True},
    'reads-32': {'request_batch': 32, 'share_requests': True, 'share_parents': True, 'tables_only': True},
    'stream-8': {'request_batch': 8, 'share_requests': True, 'share_parents': True, 'stream_requests': True},
    'shared-32': {'request_batch': 32, 'share_requests': True},
}


def make_request(case, seed, args):
    name = f'{case}-{seed}'
    bundle = args.bundles / name
    program = bundle / 'program.json'
    req = read(bundle / 'request.json')
    assert hashlib.sha256(program.read_bytes()).hexdigest() == req['source_sha256']
    assert not req['multi_residual'] and not read(bundle / req['single_config'])['residual']
    for k in ('single_config', 'merge_config'):
        req[k] = str(bundle / req[k])
    cfg = args.out / f'{name}-root.json'
    cfg.write_text(json.dumps(dict(read(bundle/'root.json'), encoding='checked_slots', forbid_fallback=True)))
    req.update(root_config=str(cfg), multi_weights=str(args.tables/f'{name}-tied.json'), radius=0,
               baked_codes=str(args.tables/f'{name}-tied.bin'), baked_row_index=False, packed_lookup=True,
               multi_mode='rowdeltapairguardstackseallearned',
               rows=dict(action=4, max_rows=1, workers=1, batch=True, verify=2))
    return req, program, bundle


def run(case, seed, args):
    name = f'{case}-{seed}'
    req, program, bundle = make_request(case, seed, args)
    with session(args.vanilla/'vanilla-audit', program) as audit:
        gold = audit({'audit': True})
    result = {'vanilla': dict(rhs=gold['rhs_count'], runs=gold['runs'], ms=[])}
    with ExitStack() as stack:
        cpu = stack.enter_context(session(args.vanilla/'vanilla',program))
        infer = stack.enter_context(session(args.native,program,bundle/'plans.json'))
        for arm, delta in ARMS.items():
            output = infer(dict(req, **delta, audit=True))
            v = compare(output, gold)
            assert v['aligned'] and all(v['checks'].values()), (case, arm, v)
            assert v['rhs'] == v['neural_rhs'] == gold['rhs_count']
            assert 100*v['direct_cells'] >= 98*v['fresh']
            v.update(requests=output['multi']['transactions'],
                     point_reads=output['multi']['counts']['point_reads'],
                     primitive_evals=output['multi']['counts']['primitive_evals'],
                     ms=[])
            v['request_digest'] = output['multi']['request_digest']
            assert isinstance(v['request_digest'],str) and len(v['request_digest']) == 64
            if arm != 'immediate':
                base = result['immediate']
                for field in ('raw','commits','physical','multi','children','cells','emitted','applied','root_allocated','request_digest'):
                    assert v[field] == base[field], (name,arm,field)
                work = v['requests']
                assert 0 < work['peak_lanes'] <= delta['request_batch'] and work['lanes'] >= work['survivors']
                if 'transaction-1' in result:
                    assert work['parent_reads'] + work['reused_parents'] == result['transaction-1']['requests']['parent_reads']
                assert v['point_reads'] + work['reused_rows'] == base['point_reads']
                assert v['primitive_evals'] + work['reused_scalars'] == base['primitive_evals']
                if arm == 'stream-8':
                    matched = result['parents-8']['requests']
                    for f in ('lanes','survivors','raw_batches','parent_reads','reused_parents','reads','evaluations','reused_rows','reused_scalars'):
                        assert work[f] == matched[f], (case,arm,f,work[f],matched[f])
                    assert work['peak_lanes'] == 1
                diagnostic = infer(dict(req, **delta, request_profile=True, audit=False))
                assert diagnostic['state_sha'] == gold['state_sha'] and diagnostic['runs'] == gold['runs']
                prof = diagnostic['multi']['transactions']
                v['diagnostic_ns'] = {key: prof[key] for key in ('collect_ns','max_collect_ns','execute_ns')}
            result[arm] = v
        names = list(result)
        for t in range(args.repeats+1):
            off = t%len(names)
            order = names[off:] + names[:off]
            for arm in order if t%2 == 0 else reversed(order):
                out = cpu({}) if arm == 'vanilla' else infer(dict(req, **ARMS[arm], audit=False))
                assert out['state_sha'] == gold['state_sha'] and out['runs'] == gold['runs']
                if arm != 'vanilla':
                    assert out['root_recipe']['allocated'] == result[arm]['root_allocated']
                    assert out['multi']['transactions'] == result[arm]['requests']
                if t:
                    result[arm]['ms'].append(out['ms'])
    for v in result.values():
        v['median_ms'] = median(v['ms'])
    print(name, {k: round(v['median_ms'],2) for k,v in result.items()}, flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('native','vanilla','bundles','tables','out'): p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703])
    p.add_argument('--repeats',type=int,default=6)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    results={}
    for case in a.cases:
        for seed in a.seeds:
            results[f'{case}/{seed}']=run(case,seed,a)
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
