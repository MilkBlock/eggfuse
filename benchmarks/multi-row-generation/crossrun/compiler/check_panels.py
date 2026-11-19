"""Offline comparison of every evaluation label with both actual Cell CPU Runs."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from build_request import HERE, make_case
from extract import digest, lower, require, validate_case

sys.path.insert(0, str(HERE.parent/'data'))
from crossrun_data import dataset


def fixture(split, index, panel):
    def table(name):
        return [[i, *values] for i, values in enumerate(panel[name][index].tolist())]
    return {'id': f'{split}-{index}', 'A': table('a'), 'B': table('b'),
            'Request': panel['requests'][index].tolist()}


def check_split(split, executable, plan, work):
    rules = (HERE/'rules.egg').read_text()
    panel = dataset(split)
    count = len(panel['a'])
    row_counts = [0, 0]
    nonempty = [0, 0]
    accepted_hash = hashlib.sha256()
    for lo in range(0, count, 16):
        indices = range(lo, min(count, lo+16))
        cases = [make_case(fixture(split, i, panel), rules) for i in indices]
        source = work/'request.json'
        target = work/'compiled.json'
        source.write_text(json.dumps({'cases': cases}))
        subprocess.run([executable,source,target], check=True)
        records = json.loads(target.read_text())['cases']
        require(len(records) == len(cases), 'missing runtime results')
        for i, runtime in zip(indices, records):
            require(runtime['id'] == f'{split}-{i}', 'input order mismatch')
            compiled = lower(runtime['compiled_program']['recipe'])
            require(compiled == plan['rules'], 'runtime program does not share the neural template')
            reports = validate_case(runtime, compiled)['runs']
            for stage, labels in enumerate(('target1','target2')):
                rows = panel[labels][i]
                expected = sorted(tuple(row[1:]) for row in rows.tolist() if row[0] == 1)
                observed = reports[stage]['published_rows']
                require(observed == expected, f'{split}[{i}] disagrees at Run {stage+1}')
                row_counts[stage] += len(observed)
                nonempty[stage] += bool(observed)
                accepted_hash.update(json.dumps([i,stage+1,observed],separators=(',',':')).encode() + b'\n')
    return dict(graphs=count, published_rows=row_counts, nonempty_graphs=nonempty,
                ordered_publications_sha256=accepted_hash.hexdigest(),
                input_sha256=digest(b''.join(panel[k].tobytes() for k in ('a','b','requests'))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    plan = json.loads((HERE/'plan.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        reports = {name: check_split(name, args.executable.resolve(), plan, Path(tmp))
                   for name in ('iid','left_collision','right_collision')}
    args.report.write_text(json.dumps({'source_sha256': digest((HERE.parent/'data/crossrun_data.py').read_bytes()),
                                       'binary_sha256': digest(args.executable.read_bytes()),
                                       'splits': reports}, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
