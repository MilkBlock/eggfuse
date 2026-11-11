#!/usr/bin/env python3
"""Check saved batch observations, typed implications and Bloom maintenance."""
from collections import Counter
from functools import cache
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def implications(specs, classes):
    # A stronger tree has all of the weaker tree's projected necessary guards.
    # Table and projected-column order are part of the proof, never just arity.
    for i, spec in enumerate(specs):
        assert all(child < i for child, _ in spec['guards']), 'expected the compiled acyclic condition graph'

    @cache
    def subset(strong, weak):
        if strong == weak: return True
        a, b = specs[strong], specs[weak]
        return (a['table'] == b['table'] and a['cols'] == b['cols'] and
                all(any(ac == bc and subset(ai, bi) for ai, ac in a['guards'])
                    for bi, bc in b['guards']))

    @cache
    def entails(strong, weak):
        a, b = classes[strong], classes[weak]
        return (a['driver'] == b['driver'] and
                all(any(ac == bc and subset(ai, bi) for ai, ac in a['guards'])
                    for bi, bc in b['guards']))
    return entails


def dominance(audit):
    assert audit['dropped_events'] == 0
    entails = implications(audit['specs'], audit['classes'])
    seen, epoch = {}, None
    counts = Counter()
    pairs = Counter()
    for current, node, watermark, cls, rows, probes, rejected in audit['events']:
        if current != epoch:
            seen.clear(); epoch = current
        prior = seen.setdefault((node, watermark), set())
        counts['observed_batches'] += 1
        counts['observed_rows'] += rows
        counts['observed_probes'] += probes
        witnesses = [old for old in sorted(prior) if entails(cls, old)]
        if witnesses:
            old = cls if cls in witnesses else witnesses[0]
            counts['potential_batches'] += 1
            counts['potential_rows'] += rows
            counts['potential_probes'] += probes
            counts['observed_rejections_in_potential_batches'] += rejected
            counts['partial_rejection_batches'] += rejected != rows
            kind = 'identical' if cls == old else 'implied'
            counts[kind + '_batches'] += 1
            counts[kind + '_probes'] += probes
            pairs[old, cls] += 1
        if rejected == rows:
            counts['fully_rejected_batches'] += 1
            prior.add(cls)
        counts['peak_negative_records'] = max(counts['peak_negative_records'], sum(map(len, seen.values())))
    return {'scope':'offline implication opportunity, not an implemented takeover or latency estimate',
            'counts':dict(counts), 'transition_pairs':[
                {'weak':a,'strong':b,'batches':n} for (a,b),n in pairs.most_common()]}


def signature(report):
    keys = ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')
    rows = [[s[k] for k in keys] for s in report['steps']]
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


def collect(root, output):
    result = {'baseline_commit':'ac850f2c', 'scope':'standalone Cell CPU; diagnostics, not timing or native egglog', 'cases':{}}
    reviewed=read(Path(__file__).resolve().parent.parent/'cell-absorption-guard/kernels.json')
    for case in ('sum','ray1280','ray-full'):
        before, after = [root / name for name in (case,case+'-after')]
        a,b = [read(p/'report.json') for p in (before,after)]
        control=root.parent/'cell-absorption-kernels'/case
        assert sha(control/'report.json')==reviewed['cases'][case]['reports_sha256'][1]
        c=read(control/'report.json')
        assert sha(control/'state.json')==sha(before/'state.json') and signature(c)==signature(a)
        for key in ('stats','free_join','entry_schedule','key_lookup_calls'): assert c[key]==a[key]
        original=a['sieve'].copy(); original.pop('entry_admission_audit')
        assert original==c['sieve']
        assert sha(before/'state.json') == sha(after/'state.json')
        assert signature(a) == signature(b)
        for key in ('stats','program_sha256','prefix_configuration','key_lookup_calls','free_join','entry_schedule'):
            assert a[key] == b[key], (case,key)
        old,new = [r['sieve'].copy() for r in (a,b)]
        bloom = [s.pop('bloom_bytes') for s in (old,new)]
        assert old == new
        audit = a['sieve']['entry_admission_audit']
        fields = ('batches','rows','probes','rejects','reused_batches','repeated_rows','repeated_probes','repeated_rejects')
        totals = {k:sum(c[k] for c in audit['classes']) for k in fields}
        record = result['cases'][case] = {'runs':len(a['steps']), 'state_sha256':sha(after/'state.json'),
            'ordered_run_sha256':signature(b),'exact_state_effects_and_admission_counts':True,
            'bloom_bytes':bloom, 'ordinary_sieve_probes':a['sieve']['stats']['probes'],
            'batch_audit':{k:v for k,v in audit.items() if k not in ('classes','events','specs')},
            'classes':len(audit['classes']),'statically_shared_classes':sum(len(c['consumers'])>1 for c in audit['classes']),
            'totals':totals,'report_sha256':[sha(p/'report.json') for p in (before,after)]}
        if case in ('sum','ray-full'):
            path = root / ('sum-dominance' if case == 'sum' else 'ray-dominance')
            d = read(path/'report.json')
            assert sha(path/'state.json') == record['state_sha256'] and signature(d) == signature(b)
            for k in ('stats','free_join','entry_schedule','key_lookup_calls'): assert d[k] == b[k]
            extended = d['sieve'].pop('entry_admission_audit')
            original = b['sieve'].pop('entry_admission_audit')
            assert d['sieve'] == b['sieve'] and extended['classes'] == original['classes']
            assert len(extended['events']) == totals['batches']
            record['dominance'] = dominance(extended)
            record['dominance_report_sha256'] = sha(path/'report.json')
    before,after=[root/name for name in ('sum-collision-before','sum-collision-after')]
    a,b=[read(p/'report.json') for p in (before,after)]
    assert sha(before/'state.json')==sha(after/'state.json') and signature(a)==signature(b)
    for key in ('stats','free_join','entry_schedule','key_lookup_calls'): assert a[key]==b[key]
    result['forced_zero_bit_fingerprints']={'exact_state_work_and_runs':True,
        'state_sha256':sha(after/'state.json'),'reports_sha256':[sha(p/'report.json') for p in (before,after)]}
    acceptance=read(root/'semantic-acceptance.json')
    assert acceptance['status']=='pass'
    assert acceptance['input_sha256']['cpu_values']==result['cases']['sum']['state_sha256']
    result['native_sum_acceptance_sha256']=sha(root/'semantic-acceptance.json')
    result['binaries']={name:sha(root/name) for name in ('observer','observer-after','observer-dominance')}
    output.write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    if not __debug__: raise SystemExit('run without Python -O')
    collect(*map(Path,sys.argv[1:]))
