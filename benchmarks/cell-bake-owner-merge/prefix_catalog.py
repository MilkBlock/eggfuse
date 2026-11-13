#!/usr/bin/env python3
"""Same-executable full-RHS vs checked-prefix witness catalog comparison.
Run the whole script through eggfuse-job --kind compute. This is not timing.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')


def read(path):
    return json.loads(path.read_text())


def run(binary, root, output):
    full_observation = root / 'prefix-full-observation'
    for case in CASES:
        observed = read(root / 'prefix-observation' / case / 'witness-observation.json')
        if observed['all_saved_run_checks_equal'] is not True or observed['terminal_check_equal'] is not True:
            raise ValueError('unaudited observation')
        saturation = observed['catalog_trace']['saturation']
        recipes = saturation['witness_recipes']
        if any(r.get('coverage') not in ('full_rhs', 'checked_prefix') for r in recipes):
            raise ValueError('old or unknown recipe coverage')
        saturation['witness_recipes'] = [r for r in recipes if r['coverage'] == 'full_rhs']
        directory = full_observation / case
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'witness-observation.json').write_text(json.dumps(observed))
    for source, variant in [('prefix-full-observation', 'prefix-full'), ('prefix-observation', 'prefix-all')]:
        subprocess.run([str(binary), 'apply-witnesses', str(root), source, variant], check=True)
        subprocess.run([str(binary), 'check-passive', str(root), variant], check=True)
    reports = {variant: {r['case']: r for r in read(root / variant / 'checked.json')['cases']}
               for variant in ('prefix-full', 'prefix-all')}
    rows = []
    for case in CASES:
        control, candidate = [reports[v][case] for v in ('prefix-full', 'prefix-all')]
        if control['final_state'] != candidate['final_state'] or control['runs'] != candidate['runs']:
            raise ValueError('state or Run mismatch')
        if not all(r['all_saved_run_checks_equal'] is True for r in (control, candidate)):
            raise ValueError('missing Run validation')
        stripped = []
        for variant in ('prefix-full', 'prefix-all'):
            artifact = read(root / variant / case / 'candidate.json')
            artifact.pop('sha256')
            artifact.pop('ownership_witnesses')
            stripped.append(artifact)
        if stripped[0] != stripped[1]:
            raise ValueError('comparison changed more than witness catalogs')
        metrics = {}
        for label, report, variant in [('full_only', control, 'prefix-full'), ('including_prefix', candidate, 'prefix-all')]:
            artifact = read(root / variant / case / 'candidate.json')
            recipes = artifact['ownership_witnesses']['recipes']
            stats = report['runtime_stats']
            metrics[label] = dict(program=report['program'], recipes=len(recipes),
                key_lookup_calls=report['key_lookup_calls'],
                route_probes=stats['constructor_cell_route_probes'],
                route_accepted=stats['constructor_cell_route_accepted'],
                alternative_checks=stats['constructor_cell_route_alternative_checks'],
                alternative_fields=stats['constructor_cell_route_alternative_fields'],
                static_key_admissions=stats['constructor_cell_route_key_proved'],
                compared_admissions=stats['constructor_cell_route_compared_admissions'])
        rows.append(dict(case=case, runs=control['runs'], all_saved_run_checks_equal=True,
            final_state=control['final_state'],
            key_lookups_saved=control['key_lookup_calls']-candidate['key_lookup_calls'], **metrics))
    result = dict(scope='Actual standalone Cell runtime; same binary, catalog-only ablation; no timing or memory claim',
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), cases=rows)
    output.write_text(json.dumps(result, indent=2) + '\n')
    for row in rows:
        print(row['case'], row['key_lookups_saved'])


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3]))
