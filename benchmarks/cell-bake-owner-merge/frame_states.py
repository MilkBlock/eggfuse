#!/usr/bin/env python3
"""Locate duplicate default fact state in saved cross-stage instance snapshots."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def collect(root):
    rows = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        path = root / f'{case}-seed.json'
        data = json.loads(path.read_text())
        frames = {f['cell']: f for f in data['source_storage']['fact_lifecycle']['frames']}
        components = data['ownership_storage']['components']
        ids = [i for c in components for i in c['frames']]
        if len(ids) != len(set(ids)):
            raise ValueError(f'{case}: ambiguous frame ownership')
        for c in components:
            actual = sum(s['owned'] for i in c['frames'] if i in frames for s in frames[i]['facts'])
            if actual != c['live_facts']:
                raise ValueError(f'{case}: component/fact lifetime mismatch')
        live = [frames[i] for i in ids if i in frames]
        patterns = Counter((f['template'], tuple(s['op'] for s in f['facts'])) for f in live)
        facts = [(f, s) for f in live for s in f['facts']]
        default = sum(f['completed'] and s['owned'] and not s['hidden'] and s['entry'] is None
                      and not s['local_union_owned'] and not s['decoded']
                      and s['epoch'] == f['started_epoch'] and s['born'] == f['started_epoch']
                      for f, s in facts)
        inherited = data['source_storage']['completed_owners']['inherited_fact_lifecycles']
        if inherited > default:
            raise ValueError(f'{case}: inconsistent inherited lifecycle subset')
        rows.append(dict(case=case, input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            program=data['program_sha256'], composition_frames=len(ids),
            absent_source_records=len(ids)-len(live), live_source_records=len(live),
            empty_source_records=sum(not f['facts'] for f in live),
            parent_linked_source_records=sum(f['parent'] is not None for f in live),
            incomplete_source_records=sum(not f['completed'] for f in live),
            live_facts=len(facts), default_lifecycle_facts=default,
            already_inherited_lifecycles=inherited,
            remaining_default_lifecycles=default-inherited,
            distinct_template_operation_patterns=len(patterns),
            frames_in_repeated_patterns=sum(n for n in patterns.values() if n > 1),
            patterns=[dict(template=t, operations=list(ops), instances=n)
                      for (t, ops), n in sorted(patterns.items())]))
    return dict(scope='Saved final standalone Cell runtime state; potential representation sharing, not saved bytes or skipped effects',
        obligations=['Default lifecycle does not imply identical values, results, hashes or equivalence classes.',
                     'Observed operation sets include dynamic reuse/deletion outcomes; template alone does not prove their presence.',
                     'Absent source records may still have static frame identities used by live sibling wiring.',
                     'Keep late matches, actual foreign results, visibility, generations and original Run boundaries.'],
        cases=rows)


if __name__ == '__main__':
    result = collect(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    for r in result['cases']:
        print(r['case'], r['live_source_records'], r['default_lifecycle_facts'], r['live_facts'])
