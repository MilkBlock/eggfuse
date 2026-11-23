"""Mutate one named premise at a time on the recursive-parents fixture."""
import argparse
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from study import compare, invoke


def run(binary, program):
    with TemporaryDirectory() as directory:
        tape = Path(directory) / 'tape.json'
        def execute(role):
            return invoke(binary, role, program, tape, True, None)
        ref = execute('reference')
        compare(execute('capture'), ref)
        original = json.loads(tape.read_bytes())
        requests = original['requests']
        join = next(i for i, r in enumerate(requests) if len(r['parents']) > 1)
        producer = {r['token']: r for r in requests}
        def issued_parent(p):
            owner = producer[p['address']['token']]
            return any(other['rule'] == owner['rule'] and other is not owner for other in requests)
        parent = next(i for i,p in enumerate(requests[join]['parents']) if issued_parent(p))
        selected = requests[join]['parents'][parent]
        owner = producer[selected['address']['token']]
        peer = next(r for r in requests if r['rule'] == owner['rule'] and r is not owner)
        recipe = json.loads(program.read_bytes())['recipe']['rules'][owner['rule']]['effects']
        pc = selected['address']['op']
        other_op = next(i for i,op in enumerate(recipe)
                        if i != pc and op.get('call') == recipe[pc]['call'])
        others = [r for r in requests if any(p['address']['token'] == requests[join]['token']
                                             for p in r['parents'])]
        assert len(others) == 1
        for name, change, reason in (
            ('wrong instance', lambda r: r['address'].update(token=peer['token']), 'binding'),
            ('wrong instruction', lambda r: r['address'].update(op=other_op), 'binding'),
            ('stale', lambda r: r.update(version=r['version'] + 1), 'version'),
            ('future self', lambda r: r['address'].update(token=requests[join]['token']), 'unknown_output'),
        ):
            mutant = copy.deepcopy(original)
            change(mutant['requests'][join]['parents'][parent])
            tape.write_text(json.dumps(mutant))
            result = execute('replay')
            if (not result['counts']['rejected'].get(reason)
                or result['matches'] != ref['matches'] - 2 or result['state_sha'] == ref['state_sha']):
                raise ValueError((name, result['counts']))
        renamed = copy.deepcopy(original)
        ids = {r['token']: 2**31 - r['token'] for r in requests}
        for r in renamed['requests']:
            r['token'] = ids[r['token']]
            for p in r['parents']:
                addr = p['address']
                addr['token'] = ids.get(addr['token'], addr['token'])
        renamed['requests'].reverse()
        tape.write_text(json.dumps(renamed))
        compare(execute('replay'), ref)
        print('wrong instance, wrong instruction, stale version, future reference, renamed/reordered tape: pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('program', type=Path)
    args = parser.parse_args()
    run(args.binary.resolve(), args.program.resolve())
