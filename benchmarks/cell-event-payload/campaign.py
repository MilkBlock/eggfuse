#!/usr/bin/env python3
"""Run the frozen periodic lanes, retaining separate background observations."""
import datetime
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading


def sample():
    # macOS ps can truncate a multibyte process name. Preserve the observation
    # with replacement characters; compiler names and numeric CPU fields are ASCII.
    processes = subprocess.check_output(['ps', '-axo', 'pid,comm,pcpu'], text=True, errors='replace')
    compilers = []
    for line in processes.splitlines()[1:]:
        words = line.split(None, 1)
        if len(words) != 2:
            continue
        command = words[1].rsplit(None, 1)[0]
        if Path(command).name in ('cargo', 'rustc', 'clang', 'ld', 'cc'):
            compilers.append(line)
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'processes': processes, 'compiler_processes': compilers}


def main(root):
    assert not any((root / f'timing-{c}').exists() for c in ('sum', 'ray')), 'never overwrite a campaign'
    first = sample()
    assert not first['compiler_processes'], first['compiler_processes']
    (root / 'background-observation.json').write_text(json.dumps(dict(first, platform=platform.platform()), indent=2) + '\n')
    stop = threading.Event()
    errors = []

    def observe():
        try:
            with (root / 'background-samples.jsonl').open('w') as stream:
                while not stop.is_set():
                    row = sample()
                    row['nonzero_cpu_processes'] = [line for line in row.pop('processes').splitlines()[1:]
                                                   if float(line.rsplit(None, 1)[-1]) > 0]
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                    stop.wait(5)
        except Exception as e:
            errors.append(repr(e))

    monitor = threading.Thread(target=observe)
    monitor.start()
    try:
        for case, repeat in (('sum', 5), ('ray', 3)):
            print('start timing', case, flush=True)
            with (root / f'timing-{case}.log').open('w') as log:
                result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / 'witness-prefix/measure.py'),
                    str(root / f'{case}-manifest.json'), str(root / f'timing-{case}'),
                    '--repeat', str(repeat), '--warmups', '1', '--timeout', '120'],
                    stdout=log, stderr=subprocess.STDOUT)
            print('finished timing', case, result.returncode, flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)
    finally:
        stop.set()
        monitor.join()
    assert not errors, errors


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main(Path(sys.argv[1]).resolve())
