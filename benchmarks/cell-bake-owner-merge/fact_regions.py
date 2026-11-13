#!/usr/bin/env python3
"""Measure actual completed fact membership against shared template operations."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def analyze(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    ownership = data['ownership_storage']
    directory = {}
    for component in ownership['components']:
        shape = ownership['shapes'][component['shape']]
        for ordinal, cell in enumerate(component['frames']):
            if cell in directory:
                raise ValueError('duplicate composition source')
            fields = ownership['programs'][shape['programs'][ordinal]]['fields']
            directory[cell] = tuple(i for i, columns in enumerate(fields) if columns)
    patterns = Counter()
    templates = {}
    counts = Counter()
    for frame in data['source_storage']['fact_lifecycle']['frames']:
        if not frame['completed_storage']:
            counts['ordinary_sources_excluded'] += 1
            continue
        nominal = directory[frame['cell']]
        previous = templates.setdefault(frame['template'], nominal)
        if previous != nominal:
            raise ValueError('template has inconsistent field layouts')
        actual = tuple(f['op'] for f in frame['facts'])
        if len(set(actual)) != len(actual) or actual != tuple(sorted(actual)):
            raise ValueError('nonunique or unsorted facts')
        if not set(actual) <= set(nominal):
            raise ValueError('fact outside template layout')
        if not all(f['owned'] and not f['decoded'] and f['entry'] is None
                   and not f['local_union_owned'] for f in frame['facts']):
            raise ValueError('completed owned representation contract')
        counts['completed_sources'] += 1
        counts['present_facts'] += len(actual)
        counts['nominal_fact_positions'] += len(nominal)
        counts['absent_positions'] += len(nominal) - len(actual)
        counts['full_membership_sources'] += actual == nominal
        counts['partial_membership_sources'] += actual != nominal
        default = sum(not f['hidden'] and f['epoch'] == f['born'] == frame['started_epoch']
                      for f in frame['facts'])
        counts['stage_default_facts'] += default
        counts['lifecycle_exception_facts'] += len(actual) - default
        patterns[(frame['template'], actual)] += 1
    if counts['completed_sources'] != data['source_storage']['completed_owners']['completed_frames']:
        raise ValueError('incomplete source census')
    rows = [dict(template=t, present_ops=list(ops), sources=n,
                 nominal_ops=list(templates[t]))
            for (t, ops), n in sorted(patterns.items(), key=lambda item: (-item[1], item[0]))]
    return dict(input_sha256=hashlib.sha256(raw).hexdigest(),
                program_sha256=data['program_sha256'], counts=dict(counts),
                distinct_membership_patterns=len(rows),
                sources_in_repeated_patterns=sum(n for n in patterns.values() if n > 1),
                largest_partial_patterns=[row for row in rows if row['present_ops'] != row['nominal_ops']][:12])


if __name__ == '__main__':
    root = Path(sys.argv[1])
    result = dict(scope='Frozen standalone runtime; exact observed membership, not compiler proof or saved bytes',
                  cases={case: analyze(root / (case + '-pooled.json'))
                         for case in ('fact', 'loopfact', 'sum-bits', 'dot-product')})
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    for case, row in result['cases'].items():
        print(case, row['counts'], row['distinct_membership_patterns'])
