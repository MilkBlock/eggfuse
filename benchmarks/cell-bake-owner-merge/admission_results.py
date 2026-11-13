#!/usr/bin/env python3
"""Summarize passive cross-stage admissions, keeping frame and anchor counts distinct."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ANCHOR_OUTCOMES = ('anchor_not_fact', 'anchor_not_owned', 'anchor_missing_frame',
                   'frame_limit', 'source_order', 'transition_not_baked', 'joined')


def collect(root):
    result = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        path = root / case / 'witness-checked.json'
        report = json.loads(path.read_text())
        if report['all_saved_run_checks_equal'] is not True:
            raise ValueError(f'{case}: unverified replay')
        trace = report['catalog_trace']
        grouped = defaultdict(Counter)
        for row in trace['admissions']:
            grouped[(row['rule'], row['template'])][row['reason']] += row['count']
        totals = Counter()
        for counts in grouped.values():
            if counts['birth'] != counts['joined'] + counts['fallback']:
                raise ValueError(f'{case}: frame accounting')
            if counts['anchor_attempt'] != sum(counts[k] for k in ANCHOR_OUTCOMES):
                raise ValueError(f'{case}: anchor accounting')
            if counts['joined_cross_stage'] > counts['joined']:
                raise ValueError(f'{case}: cross-stage accounting')
            totals.update(counts)
        if totals['fallback'] != trace['uncovered_births']:
            raise ValueError(f'{case}: fallback accounting')
        top = sorted(grouped.items(), key=lambda item: (-item[1]['transition_not_baked'],
                                                       -item[1]['fallback'], str(item[0])))[:12]
        result.append(dict(case=case, input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            program=report['program'], runs=report['runs'], all_saved_run_checks_equal=True,
            totals=dict(totals), top_unbaked_rules=[dict(rule=key[0], template=key[1], counts=dict(counts))
                                                 for key, counts in top]))
    return dict(scope='Actual standalone Cell runtime; passive same-source Run/effect checks; no native acceptance or timing claim',
                counting='birth/join/fallback count newly created composition frames; anchor reasons count alternatives and may overlap per frame; not attribution of final singletons',
                cases=result)


if __name__ == '__main__':
    report = collect(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2) + '\n')
    for row in report['cases']:
        print(row['case'], row['totals'])
