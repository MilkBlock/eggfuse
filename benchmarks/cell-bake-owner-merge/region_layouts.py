#!/usr/bin/env python3
"""Offline region membership census; observations never authorize RHS skipping."""
import collections
import hashlib
import json
import sys
from pathlib import Path

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')


def analyze(report):
    frames = report['source_storage']['fact_lifecycle']['frames']
    sources = {f['cell']: f for f in frames}
    if len(sources) != len(frames):
        raise ValueError('duplicate source identity')
    ownership = report['ownership_storage']
    groups = collections.Counter()
    widths = collections.Counter()
    counts = collections.Counter()
    seen = set()
    for component in ownership['components']:
        ids, codes = component['frames'], component['frame_codes']
        shape = ownership['shapes'][component['shape']]
        if len(ids) != len(codes) or len(ids) != len(shape['programs']):
            raise ValueError('inconsistent region extent')
        if seen.intersection(ids) or len(set(ids)) != len(ids):
            raise ValueError('duplicate wiring identity')
        seen.update(ids)
        membership, epochs = [], []
        live = retained = 0
        for cell, program in zip(ids, shape['programs']):
            source = sources.get(cell)
            if source is None:
                membership.append(None)
                counts['wiring_only_sources'] += 1
                continue
            ops = tuple(sorted(f['op'] for f in source['facts']))
            if len(set(ops)) != len(ops):
                raise ValueError('duplicate fact operation')
            fields = ownership['programs'][program]['fields']
            if any(op >= len(fields) or not fields[op] for op in ops):
                raise ValueError('fact absent from static operation layout')
            membership.append(ops)
            live += len(ops)
            retained += source['retainers'] > 0
            epochs.append(source['started_epoch'])
            counts['stored_sources'] += 1
            counts['incomplete_sources'] += not source['completed']
            counts['lifecycle_exceptions'] += sum(
                f['born'] != source['started_epoch'] or f['epoch'] != source['started_epoch'] or f['hidden']
                for f in source['facts'])
        if live != component['live_facts']:
            raise ValueError('component live facts do not reconcile')
        counts['live_facts'] += live
        counts['externally_retained_sources'] += retained
        counts['regions_with_external_readers'] += retained > 0
        counts['cross_epoch_regions'] += len(set(epochs)) > 1
        widths[len(ids)] += 1
        # IDs/values/absolute epochs are intentionally excluded. Shape IDs are
        # valid only inside this artifact; never join them across programs.
        key = (component['shape'], tuple(codes), tuple(membership))
        groups[key] += 1
    counts['regions'] = sum(groups.values())
    counts['membership_layouts'] = len(groups)
    counts['regions_in_repeated_layouts'] = sum(n for n in groups.values() if n > 1)
    counts['multi_source_regions'] = sum(n for width, n in widths.items() if width > 1)
    counts['source_headers_above_one_per_region'] = counts['stored_sources'] - counts['regions']
    return dict(counts=dict(counts), widths=dict(sorted(widths.items())),
        pattern_multiplicities=dict(sorted(collections.Counter(groups.values()).items())))


def batch(root):
    rows = []
    for case in CASES:
        path = root / f'{case}-candidate.json'
        raw = path.read_bytes()
        report = json.loads(raw)
        rows.append(dict(case=case, input_sha256=hashlib.sha256(raw).hexdigest(),
            program=report['program_sha256'], final_state=report['final_state_sha256'],
            runs=report['runs'], **analyze(report)))
    return dict(scope='Final standalone Cell CPU snapshots; not a lifetime peak or executable coverage proof',
        limitations=[
            'Equal membership does not prove equal values, Eq, visibility or legal RHS reuse.',
            'Different started epochs do not identify source Run boundaries.',
            'Missing source storage is not permission to delete static wiring.',
            'One header per region is a structural sensitivity count, not removable bytes.',
            'Shapes are artifact-local; no cross-workload deduplication is claimed.',
        ], cases=rows)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(batch(Path(sys.argv[1])), indent=2) + '\n')
