"""Pool checked Cell traces by static definition, never by sample-local IDs."""
import collections
import hashlib
import json
import sys
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def pool(samples):
    if len({name for name, _, _ in samples}) != len(samples):
        raise ValueError('duplicate sample name')
    if not samples:
        raise ValueError('empty batch')
    tables = canonical(samples[0][1]['tables'])
    for name, interface, profile in samples:
        if canonical(interface['tables']) != tables:
            raise ValueError(f'{name}: table contract differs; explicit typed mapping required')
        if profile['source'] != interface['profile_source']:
            raise ValueError(f'{name}: trace belongs to a different source')
        if profile['schema'] != samples[0][2]['schema']:
            raise ValueError('profile schema differs')
    roots = sorted({canonical(p) for _, i, _ in samples for p in i['programs']})
    rules = sorted({canonical(p) for _, i, _ in samples for p in i['rules']})
    root_ids = {p: n for n, p in enumerate(roots)}
    rule_ids = {p: n for n, p in enumerate(rules)}
    combined = {}
    for name, interface, profile in samples:
        for record in profile['records']:
            f = record['fragment']
            portable = dict(root=root_ids[canonical(interface['programs'][f['root']])], hops=[])
            for hop in f['hops']:
                h = dict(hop)
                h['entry'] = interface['entries'][hop['rule']][hop['entry']]
                h['rule'] = rule_ids[canonical(interface['rules'][hop['rule']])]
                portable['hops'].append(h)
            key = canonical(portable)
            if key not in combined:
                combined[key] = dict(fragment=portable, static_instruction_handles=record['static_instruction_handles'],
                                     observed=dict(activations=0, binding_records_saved=0, transition_probes=0), samples={})
            row = combined[key]
            if row['static_instruction_handles'] != record['static_instruction_handles']:
                raise ValueError('same static fragment has inconsistent cost')
            if name in row['samples']:
                raise ValueError('ambiguous source definitions alias two records in one sample')
            row['samples'][name] = record['observed']
            for field in row['observed']:
                row['observed'][field] += record['observed'][field]
    records = [combined[k] for k in sorted(combined)]
    fingerprint = hashlib.sha256(canonical(dict(tables=tables, roots=roots, rules=rules)).encode()).hexdigest()
    merged = dict(schema=samples[0][2]['schema'], source=fingerprint, max_frames=16,
                  records=records, alternatives_overlap=True,
                  scope='pooled actual observations; canonical IDs refer to static definitions, not runtime identities')
    projected = {}
    for name, interface, _ in samples:
        root_map = {root_ids[canonical(p)]: n for n, p in enumerate(interface['programs'])}
        rule_map = {}
        for n, p in enumerate(interface['rules']):
            key = rule_ids[canonical(p)]
            if key in rule_map:
                raise ValueError('ambiguous duplicate rule definition')
            rule_map[key] = n
        local = []
        for record in records:
            f = record['fragment']
            if f['root'] not in root_map or any(h['rule'] not in rule_map for h in f['hops']):
                continue
            target = dict(root=root_map[f['root']], hops=[])
            for hop in f['hops']:
                h = dict(hop); h['rule'] = rule_map[hop['rule']]
                entries = interface['entries'][h['rule']]
                if hop['entry'] not in entries:
                    break
                h['entry'] = entries.index(hop['entry'])
                target['hops'].append(h)
            else:
                local.append(dict(record, canonical_fragment=f, fragment=target))
        projected[name] = dict(merged, source=interface['profile_source'], records=local)
    summary = dict(samples=[n for n, _, _ in samples], records=len(records),
                   shared_across_samples=sum(len(r['samples']) > 1 for r in records),
                   sample_support=dict(collections.Counter(len(r['samples']) for r in records)),
                   transferable_records={n: len(p['records']) for n, p in projected.items()},
                   scope='candidate reuse, not saved bytes or native semantic proof')
    return merged, projected, summary


if __name__ == '__main__':
    root = Path(sys.argv[1]); manifest = json.loads((root/'manifest.json').read_text())
    samples = []
    for case in manifest['cases']:
        name = case['case']; d = root/name
        samples.append((name, json.loads((d/'interface.json').read_text()), json.loads((d/'profile.json').read_text())))
    merged, projected, summary = pool(samples)
    (root/'pooled-profile.json').write_text(json.dumps(merged, indent=2)+'\n')
    (root/'pool-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    for name, profile in projected.items():
        (root/name/'pooled-profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    print(json.dumps(summary))
