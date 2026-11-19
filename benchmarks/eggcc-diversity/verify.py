"""Check original Bril and its eggcc round trip against per-case golden outputs."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(binary, args, directory, timeout):
    process = subprocess.run(
        [str(binary), *map(str, args)], cwd=directory, capture_output=True,
        timeout=timeout, env={**os.environ, 'RAYON_NUM_THREADS': '1'},
    )
    if process.returncode:
        raise RuntimeError(f'eggcc {args} exited {process.returncode}\n{process.stderr.decode()[-4000:]}')
    return process.stdout


def verify(binary, case, tmp, export, timeout):
    path = HERE / 'programs' / (case['name'] + '.bril')
    source = path.read_text()
    metadata = json.loads(run(binary, ['--run-mode', 'bril-to-json', path], tmp, timeout))
    instructions = [inst for fn in metadata['functions'] for inst in fn['instrs']]
    opcodes = collections.Counter(inst['op'] for inst in instructions if 'op' in inst)
    result = dict(source_sha256=digest(path.read_bytes()), functions=len(metadata['functions']),
                  instructions=sum(opcodes.values()), labels=sum('label' in inst for inst in instructions),
                  opcodes=dict(sorted(opcodes.items())), checked=[])
    first, rest = source.split('\n', 1)
    if first != '# ARGS: ' + ' '.join(map(str, case['examples'][0]['args'])):
        raise ValueError(f'{path.name}: header and manifest disagree')
    for test in case['examples']:
        # eggcc reads the arguments from the first Bril source line.
        argline = '# ARGS: ' + ' '.join(map(str, test['args']))
        fixture = tmp / path.name
        fixture.write_text(argline + '\n' + rest)
        expected = [str(item) for item in test['output']]
        for mode in ('parse', 'dag-round-trip'):
            actual = run(binary, ['--run-mode', mode, '--interp', fixture], tmp, timeout).decode().split()
            if actual != expected:
                raise ValueError(f'{path.name}, args {test["args"]}, {mode}: expected {expected}, got {actual}')
        result['checked'].append(test['args'])
    if export:
        options = ['--eggcc-schedule', 'parallel', '--stop-after-n-passes', '3']
        actual = run(binary, [*options, '--run-mode', 'optimize', '--interp', path], tmp, timeout).decode().split()
        if actual != [str(item) for item in case['examples'][0]['output']]:
            raise ValueError(f'{path.name}: wrong optimized output {actual}')
        content = run(binary, [*options, '--run-mode', 'egglog', path], tmp, timeout)
        if b'(run-schedule' not in content:
            raise ValueError(f'{path.name}: missing schedule in Pass 3 input')
        outname = case['name'] + '.egg'
        (export / outname).write_bytes(content)
        result['pass3'] = dict(optimized_default_output=actual, input_file=outname,
                               input_bytes=len(content), input_sha256=digest(content))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eggcc', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--pass3-dir', type=Path, help='new directory for Pass 3 inputs')
    parser.add_argument('--timeout', type=int, default=90, help='seconds per invocation')
    args = parser.parse_args()
    binary = args.eggcc.resolve(strict=True)
    if args.pass3_dir:
        args.pass3_dir.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((HERE / 'manifest.json').read_text())
    report = dict(schema=1, eggcc_binary_sha256=digest(binary.read_bytes()), cases={})
    with tempfile.TemporaryDirectory() as work:
        for case in manifest['cases']:
            name = case['name']
            print(name, flush=True)
            report['cases'][name] = verify(binary, case, Path(work), args.pass3_dir, args.timeout)
    args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
