"""Gate a single frozen routing policy across all six workload reports from study.py."""
import argparse
import json
from pathlib import Path

CASES = ('sum-bits', 'dot-product', 'gemm-bias-relu', 'stable-argmax', '3mm', 'deriche')


def assess(reports, arm):
    cases = {}
    for case in CASES:
        if case not in reports or arm not in reports[case]:
            cases[case] = {'status': 'missing'}
            continue
        report = reports[case]
        exact, candidate = report['exact'], report[arm]
        total, checks = exact['source_rhs'], exact['discovery']
        if not total or not checks or candidate['source_rhs'] != total:
            raise ValueError(f'{case}: invalid baseline')
        coverage = candidate['provider_winners']
        visits = candidate['discovery']
        budget = checks // 50
        required = (98 * total + 99) // 100
        paid = sum(candidate['paid'].values())
        eligible = candidate.get('eligible_explicit_parent_protocol', True)
        passed = eligible and coverage >= required and visits <= budget and paid > 0
        cases[case] = dict(status='pass' if passed else 'fail', winners=coverage, rhs=total,
                           required_winners=required, visits=visits, exact_visits=checks,
                           budget=budget, paid=paid, visible=candidate['visible'],
                           fept=candidate['fept'], unassisted=candidate.get('unassisted'),
                           min_multi_without_per_binding_search=max(
                               0, required-report['certified']['single_winners']-budget))
    statuses = {r['status'] for r in cases.values()}
    status = 'fail' if 'fail' in statuses else 'missing' if 'missing' in statuses else 'pass'
    return dict(arm=arm, status=status, cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--arm', required=True)
    args = parser.parse_args()
    reports = {case: json.loads(path.read_bytes()) for case in CASES
               if (path := args.directory / f'{case}.json').exists()}
    result = assess(reports, args.arm)
    print(json.dumps(result, indent=2))
    raise SystemExit({'pass': 0, 'fail': 1, 'missing': 2}[result['status']])
