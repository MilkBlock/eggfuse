"""Audit the native certificate path against independent exact executions (no training)."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(actual, reference):
    for key in ('state_sha', 'schedule', 'rhs', 'writes', 'resumes', 'events'):
        if actual[key] != reference[key]:
            delta = next((i + 1 for i, (a, b) in enumerate(zip(actual[key], reference[key]))
                          if a != b), None) if key != 'state_sha' else None
            raise ValueError(f'{key} differs at Run {delta}')


def invoke(binary, role, program, tape, audit, limit):
    cmd = [binary, role, program, tape, 'audit' if audit else 'time']
    if limit is not None:
        cmd.append(str(limit))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip())
    return json.loads(proc.stdout)


def oracle(binary, program, limit):
    with TemporaryDirectory() as tmp:
        tape = Path(tmp) / 'teacher.json'
        def run(role, audit=False):
            return invoke(binary, role, program, tape, audit, limit)
        reference = run('reference', True)
        capture = run('capture', True)
        compare(capture, reference)
        signed = json.loads(tape.read_bytes())
        replay = run('replay', True)
        if capture['runtime_events'] != replay['runtime_events'] or replay['runtime_events'] != signed['repair_events']:
            raise ValueError('repair event provenance differs')
        from collections import Counter
        emitted = {r['token']: r['run'] for r in signed['requests']}
        available = {event['token']: event['visible_from_run'] for event in signed['repair_events']}
        for event in signed['repair_events']:
            if len(event['parents']) != 2 or event['visible_from_run'] != event['run'] + 1:
                raise ValueError('invalid event boundary or input arity')
            if any(emitted.get(p['address']['token'], 0) > event['run'] for p in event['parents']):
                raise ValueError('future repair parent')
        by_kind = Counter()
        for request in signed['requests']:
            for premise in request['parents']:
                token = premise['address']['token']
                if token in available and request['run'] < available[token]:
                    raise ValueError('repair output leaked into its producing Run')
                by_kind['repair' if token in available else 'initial' if token < 0 else 'generated'] += 1
        compare(replay, reference)
        counts = replay['counts']
        if by_kind != counts['reads_by_kind']:
            raise ValueError('port-kind reference ledger differs')
        n = reference['matches']
        if not (n and counts['calls'] and counts['accepted'] == n
                and not counts['rejected'] and not counts['duplicates'] and not replay['unused']):
            raise ValueError(f'incomplete oracle control: {counts}, expected {n}')
        samples = []
        # Matched binary and inputs. Source compilation, parsing the in-memory proposal
        # stream and post-run serialization are outside each internal inference clock.
        for i in range(4):
            order = ('reference', 'replay') if i % 2 == 0 else ('replay', 'reference')
            pair = {'order': list(order)}
            for role in order:
                r = run(role)
                if r['state_sha'] != reference['state_sha'] or r['schedule'] != reference['schedule']:
                    raise ValueError('timed trajectory differs')
                pair[role] = r['seconds'] * 1000
                if role == 'replay':
                    pair['native_repair_phase_ms'] = r['repair_phase_seconds'] * 1000
                    pair['event_registration_ms'] = r['event_registration_seconds'] * 1000
                    pair['verification_ms'] = r['verify_seconds'] * 1000
                    pair['remaining_native_ms'] = pair[role] - pair['verification_ms'] - pair['event_registration_ms']
            pair['oracle_faster'] = pair['replay'] < pair['reference']
            samples.append(pair)
        return {
            'mode': 'exclusive', 'provider': 'offline_teacher', 'build_sha256': sha(binary),
            'weights_sha256': None, 'program_sha256': sha(program), 'tape_sha256': sha(tape),
            'run_limit': limit, 'source_runs_observed': replay['runs'], 'neural_waves': 0,
            'reference_commits': n, 'accepted_unique': n, 'coverage': 1, 'model_wins': 0,
            'duplicates': counts['duplicates'], 'rejected_by_reason': counts['rejected'],
            'unused': replay['unused'], 'state_sha': replay['state_sha'],
            'runtime_issued_events': len(available),
            'runtime_exported_results': sum(len(e['operations']) for e in signed['repair_events']),
            'runtime_event_proposals_charged_to_model': 0,
            'parent_refs_by_kind': {k: {'correct_teacher_reads': by_kind[k], 'required': by_kind[k]}
                                    for k in ('initial', 'generated', 'repair')},
            'resume_events': sum(x[0] for x in replay['resumes']),
            'receiver': {'loaded': True, 'invocations': counts['calls'], 'accepted': n,
                         'rejected': sum(counts['rejected'].values()), 'named_reads': counts['reads']},
            'network': {'loaded': False, 'invocations': 0, 'accepted': 0, 'rejected': 0},
            'remaining_independent_search': 0,
            'timing_ms': {key: median(s[key] for s in samples)
                          for key in ('reference', 'replay', 'verification_ms', 'event_registration_ms', 'native_repair_phase_ms', 'remaining_native_ms')},
            'network_ms': 0, 'pairs': samples,
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary', type=Path)
    p.add_argument('program', type=Path)
    p.add_argument('--limit', type=int)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = oracle(args.binary.resolve(), args.program.resolve(), args.limit)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
