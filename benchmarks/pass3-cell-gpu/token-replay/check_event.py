"""Replay must earn a repair port at the native completion boundary."""
import argparse
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from study import compare, invoke


def check(binary, program):
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'tape.json'

        def run(role):
            return invoke(binary, role, program, path, True, None)

        reference = run('reference')
        capture = run('capture')
        tape = json.loads(path.read_bytes())
        event = tape['repair_events'][0]
        uses = [(i, j) for i, req in enumerate(tape['requests'])
                for j, parent in enumerate(req['parents']) if parent['address']['token'] == event['token']]
        if not uses:
            raise ValueError('fixture did not consume its first runtime event')
        # Recorded events describe training context. They cannot mint a verifier port.
        tape['repair_events'].clear()
        path.write_text(json.dumps(tape))
        actual = run('replay')
        compare(actual, reference)
        if actual['runtime_events'] != capture['runtime_events']:
            raise ValueError('runtime depended on offline event data')
        i, j = uses[0]
        corrupt = copy.deepcopy(tape)
        corrupt['requests'][i]['parents'][j]['address']['op'] = max(event['operations']) + 1
        path.write_text(json.dumps(corrupt))
        result = run('replay')
        if not result['counts']['rejected'].get('unknown_output'):
            raise ValueError('unexported result position was admitted')
        # Submit the reference in the producing Run to an actually scheduled table atom.
        corrupt = copy.deepcopy(tape)
        req = next(r for r in corrupt['requests'] if r['run'] == event['run'] and r['parents'])
        req['parents'][0] = tape['requests'][i]['parents'][j]
        path.write_text(json.dumps(corrupt))
        result = run('replay')
        if not result['counts']['rejected'].get('unknown_output'):
            raise ValueError('same-Run repair reference was admitted')
        print('regenerated events, unexported result and producing-Run negatives: pass')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary', type=Path)
    p.add_argument('program', type=Path)
    a = p.parse_args()
    check(a.binary.resolve(), a.program.resolve())
