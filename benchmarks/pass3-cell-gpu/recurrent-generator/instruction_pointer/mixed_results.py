"""Compare two checkpoints on the same sealed native and synthetic holdouts."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def exclusive(cases):
    counts = Counter()
    rejected = Counter()
    seconds = Counter()
    for c in cases:
        if c['independent_search_calls']:
            raise ValueError(f"verifier searched on {c['case']}")
        receipt = c['counts']
        if c['issued'] != receipt['accepted'] + receipt['duplicates'] + sum(receipt['rejected'].values()):
            raise ValueError(f"incomplete proposal ledger on {c['case']}")
        counts.update({
            'programs': 1, 'correct_final_states': int(c['reference_state_equal']),
            'reference_commits': c['reference_commits'], 'reference_runs': c['reference_runs'],
            'accepted': receipt['accepted'], 'duplicates': receipt['duplicates'],
            'verifier_calls': receipt['calls'], 'issued': c['issued'], 'source_runs': c['runs'],
            'neural_waves': c['neural_waves'], 'native_repair_events': c['native_runtime_events'],
            'independent_search_calls': c['independent_search_calls'],
            'certified_reference_prefix_commits': c['certified_reference_prefix_commits'],
        })
        rejected.update(receipt['rejected'])
        for key in ('network_seconds', 'native_verify_seconds', 'native_repair_seconds',
                    'remaining_process_seconds_including_ipc', 'wall_seconds', 'reference_seconds'):
            seconds[key] += c[key]
    return dict(counts=counts, rejected=rejected, total_seconds=seconds)


def compare(root, epoch):
    manifest_path = root / 'manifest.json'
    ledger = read(root / 'ledger.json')
    training = read(epoch / 'mps-epoch.training.json')
    if training['device'] != 'mps' or sum(training['mixed_update_steps'].values()) != training['steps']:
        raise ValueError('incomplete MPS training ledger')
    groups = [v for k, v in ledger.items() if k.startswith('train/')]
    for key, measured in [('runs', 'distinct_runs'), ('programs', 'distinct_programs')]:
        if sum(g[key] for g in groups) != training[measured]:
            raise ValueError(f'training did not visit every {key}')
    baseline_audit = read(root / 'rule-head-baseline.json')
    trained_audit = read(epoch / 'rule-head.json')
    if baseline_audit['weights_sha256'] != training['initial_weights_sha256']:
        raise ValueError('unexpected starting weights')
    if trained_audit['weights_sha256'] != sha256((epoch / 'mps-epoch.pt').read_bytes()).hexdigest():
        raise ValueError('rule report used different weights')
    base = read(root / 'baseline-eval.json')
    trained = read(epoch / 'held.json')
    for attr in ('build_sha256', 'seed', 'field_pointer', 'device', 'snapshot_budget_per_case'):
        if base[attr] != trained[attr]:
            raise ValueError(f'unpaired evaluation: {attr}')
    manifest = read(manifest_path)
    pcs = Counter(pc for rec in manifest if rec['split'] == 'train'
                  for pc in rec.get('consumed_event_pcs', []))
    cases = {r['workload'] for r in manifest if r['origin'] == 'eggcc'}
    output = dict(manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(), corpus=ledger,
                  random_training_consumed_repair_pcs=pcs,
                  training={k:v for k,v in training.items() if k != 'trajectory'},
                  verifier_sha256=base['build_sha256'], inference_device=base['device'],
                  rule_head={}, holdouts={})
    for name, audit, evaluation in [('before', baseline_audit, base), ('after', trained_audit, trained)]:
        if set(audit['cases']) != cases or evaluation['splits'].keys() != base['splits'].keys():
            raise ValueError('incomplete evaluations')
        for case, strata in audit['cases'].items():
            for label in ('with_commits', 'without_commits'):
                if strata[label]['sample'] != baseline_audit['cases'][case][label]['sample']:
                    raise ValueError(f'unpaired rule sample: {case} {label}')
        output['rule_head'][name] = audit
        census = read(epoch / f'census-{name}-with-ranking.json')
        if census['weights_sha256'] != audit['weights_sha256'] or census['seed'] != audit['seed']:
            raise ValueError('rule census differs from sampled audit')
        if set(census['cases']) != {rec['workload'] for rec in manifest if rec['split'] == 'held_eggcc'}:
            raise ValueError('held rule census incomplete')
        for case, totals in census['cases'].items():
            for label in ('with_commits', 'without_commits'):
                if totals[label]['runs'] != audit['cases'][case][label]['population']:
                    raise ValueError('census missed a reference snapshot')
        held = {}
        for split, metrics in evaluation['splits'].items():
            runs = metrics['exclusive']['cases']
            def identity(c):
                return c['case'], c['reference_commits'], c['reference_runs']
            if list(map(identity, runs)) != list(map(identity, base['splits'][split]['exclusive']['cases'])):
                raise ValueError(f'unpaired programs: {split}')
            held[split] = dict(shadow=metrics['shadow'], exclusive=exclusive(runs))
            if split == 'held_eggcc':
                held[split]['exclusive_by_program'] = {c['case']:exclusive([c]) for c in runs}
        output['holdouts'][name] = dict(parameter_bytes_sha256=evaluation['weights_sha256'],
                                            rule_head_census=census, splits=held)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'epoch', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    result = compare(args.root, args.epoch)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
