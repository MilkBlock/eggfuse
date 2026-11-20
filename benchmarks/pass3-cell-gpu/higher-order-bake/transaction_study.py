"""Measure delayed typed guard evaluation after a real parent publishes a versioned SubTuple."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

from study import config, describe, make_session
from evaluate import read, rpc

HERE = Path(__file__).resolve().parent
LIMITS = (0, 1, 8, 32)


def digest(value):
    data = json.dumps(value, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def measure(args, case, seed):
    proc, req, plans, _, capture = make_session(args, case, seed)
    parent_ports = read(HERE / 'growth.json')['second_round']
    frozen = config(args, 'baked', parent_ports, recursive=True)
    arms = {}
    try:
        for limit in LIMITS:
            settings = dict(frozen, transaction_batch=limit, profile=True)
            report = rpc(proc, dict(req, higher_config=settings, audit=True))
            source = describe(report, case, args, plans, capture)
            h = report['higher']
            q = h['transactions']
            events = q.pop('source_order')
            assert len(events) == q['offered'] == q['completed']
            assert q['requests'] == h['counts'][1]
            if limit:
                assert sum(i*n for i,n in enumerate(q['requests_per_batch'])) == q['requests']
                assert 0 < q['peak'] <= limit
                assert sum(i*n for i,n in enumerate(q['batch_hist'])) == len(events)
                assert sum(q['flush_reasons']) == sum(q['batch_hist'])
            same = dict(publication_digest=digest(events), winners_digest=digest(h['winners']),
                        roots_digest=digest(report['root_recipe']['commits']),
                        state=source['graph'], counts=source['counts'])
            if arms:
                assert same == arms[0]['identity'], (case, seed, limit, 'source changed')
            arms[limit] = dict(binary_sha256=args.binary_sha256, identity=same, transactions=q, runs=source['runs'], rhs=source['rhs'],
                               direct=source['direct'], fresh=source['fresh'], neural_rhs=source['neural_rhs'],
                               winners=source['winners'], max_chain=source['max_chain'],
                               source_exact=source['source_exact'], ms=[])
        for turn in range(args.repeats+1):
            order = LIMITS[turn%4:] + LIMITS[:turn%4]
            for limit in order if turn % 2 else order[::-1]:
                report = rpc(proc, dict(req, higher_config=dict(frozen, transaction_batch=limit), audit=False))
                row = arms[limit]
                assert report['state_sha'] == row['identity']['state'] and row['runs'] == report['runs']
                assert report['higher']['transactions']['flush_reasons'] == row['transactions']['flush_reasons']
                if turn:
                    row['ms'].append(report['ms'])
    finally:
        proc.stdin.close()
        proc.wait()
    for row in arms.values():
        row['median_ms'] = median(row['ms'])
    return arms


def main(args):
    args.catalog = read(HERE / 'catalog.json')
    args.binary_sha256 = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    args.out.mkdir(parents=True, exist_ok=False)
    data = {}
    for case in args.cases:
        for seed in args.seeds:
            arms = measure(args, case, seed)
            data[f'{case}/{seed}'] = arms
            (args.out / 'results.json').write_text(json.dumps(data, indent=1)+'\n')
            print(case, seed, [(k, round(v['median_ms'], 2), v['transactions']['flush_reasons']) for k,v in arms.items()], flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for k in ('binary', 'ref', 'corpus', 'capture', 'train_capture', 'out'):
        cli.add_argument(k, type=Path)
    cli.add_argument('--cases', nargs='+', default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    cli.add_argument('--seeds', nargs='+', type=int, default=[1703,1709])
    cli.add_argument('--repeats', type=int, default=8)
    main(cli.parse_args())
