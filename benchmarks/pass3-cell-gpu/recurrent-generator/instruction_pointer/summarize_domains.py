"""Summarize complete, audited native assists. Keep each execution mode separate."""
import argparse
import json
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_bytes())


def summarize(directory):
    cases = {}
    exclusive = read(directory / 'exclusive.json')
    for path in sorted(directory.glob('*-live.json')):
        name = path.name.removesuffix('-live.json')
        live = read(path)
        replay = read(directory / f'{name}-audit.json')
        timing = read(directory / 'cost' / f'{name}.json')
        oracle = read(directory / f'oracle-{name}.json')
        if (oracle['build_sha256'] != live['receiver'] or oracle['program_sha256'] != live['program']
                or oracle['coverage'] != 1 or oracle['remaining_independent_search'] != 0):
            raise ValueError('oracle replay is incomplete or used a different build')
        ledger = live['result']
        data = replay['arms']['treatment']
        if not (live['program'] == timing['spec']['program'] == replay['program']
                and live['receiver'] == timing['spec']['binary'] == replay['receiver']['treatment']
                and live['actor'] == timing['spec']['weights'] == exclusive['weights_sha256']
                and live['stream'] == replay['issues'] and ledger['counts'] == data['counts']):
            raise ValueError(f'{name}: mismatched timing, replay or stream identities')
        if len(timing['pairs']) != 4:
            raise ValueError(f'{name}: incomplete timing series')
        samples = {arm: [] for arm in ('exact', 'oracle', 'assist')}
        for trial, entries in enumerate(timing['pairs']):
            order = ['exact', 'assist', 'oracle']
            if trial % 2:
                order.reverse()
            if [r['arm'] for r in entries] != order:
                raise ValueError('invalid trial order')
            for entry in entries:
                if entry['state_sha'] != data['state_sha']:
                    raise ValueError('timed state differs from audited replay')
                samples[entry['arm']].append(entry)
        times = {arm: {key: median(r[key] for r in rows) for key in
                       ['wall', 'inference', 'verify', 'exact'] +
                       (['rejected_seconds', 'duplicate_seconds'] if arm == 'assist' else [])}
                 for arm, rows in samples.items()}
        wins = {arm: [a['wall'] < b['wall'] for a,b in zip(samples[arm],samples['exact'],strict=True)]
                for arm in ('assist','oracle')}
        result = dict(receiver=live['receiver'], actor=live['actor'], program=live['program'],
                      requests_sha256=live['stream'], observation_sha256=data['context'], state_sha=data['state_sha'],
                      runs=data['frames'], waves=ledger['neural_waves'], required=data['commits'],
                      issued=data['issued'], verdicts=data['counts'], ports_full=ledger['visible_port_visits'],
                      ports_encoded=ledger['encoded_port_visits'], native_search={k:r['assist'] for k,r in replay['arms'].items()},
                      median_seconds=times, wins_over_exact=wins, native_oracle_ms=oracle['timing_ms'],
                      paired_wall_seconds=[[(r['arm'], r['wall']) for r in pair] for pair in timing['pairs']])
        pair_file = directory / f'{name}-pairs.json'
        if pair_file.is_file():
            pairs = read(pair_file)
            for index,pair in enumerate(pairs):
                if [r['projected'] for r in pair] != [bool(index % 2),not bool(index % 2)]:
                    raise ValueError('invalid encoder timing order')
                if any(any(row[k] != live[k] for k in ('receiver','actor','program','stream'))
                       or row['result']['counts'] != ledger['counts'] for row in pair):
                    raise ValueError('inconsistent encoder comparison')
            def walls(projected):
                return [r['wall'] for pair in pairs for r in pair if r['projected'] == projected]
            result['audited_encoder_pairs_seconds'] = dict(full=walls(False), projected=walls(True))
        screen = {}
        for arm in ('plain','screen'):
            gate = read(directory / f'{name}-{arm}.json')
            g = gate['execution']
            if gate['weights'] != live['actor'] or gate['binary'] != live['receiver'] or g['state_sha'] != data['state_sha']:
                raise ValueError('rule screen comparison differs')
            screen[arm] = dict(gate=gate['gate'], activations=gate['activations'], issued=g['issued'],
                               counts=g['counts'], residual=g['assist']['residual_commits'])
        result['rule_screen'] = screen
        cases[name] = result
    if set(cases) != {'fact','loopfact','sum-divisors'}:
        raise ValueError('missing an EggCC development holdout')
    external = exclusive['cases']
    failures = {n: dict(common_runs=external[n]['common_runs'], final_equal=external[n]['final_equal'],
                        failure=external[n]['failure']) for n in cases}
    held = [r for n,r in external.items() if n.startswith('random/')]
    return dict(assist=cases, exclusive=dict(eggcc=failures, generated=len(held),
                                             generated_equal=sum(r['final_equal'] for r in held)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.directory),indent=2)+'\n')
