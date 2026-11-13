"""Audit saved runtime state before selecting another Cell takeover mechanism.

Equal roots bound potential duplicate bindings, not equivalence of whole Cells.
No workload executions and no inference of deletability from missing local uses.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys


def census(snapshot):
    storage = snapshot['ownership_storage']
    lifecycle = snapshot['source_storage']['fact_lifecycle']['frames']
    frames = {f['cell']: f for f in lifecycle}
    if len(frames) != len(lifecycle):
        raise ValueError('duplicate source identity')
    seen = set()
    roots = collections.Counter()
    counts = collections.Counter()
    distributions = collections.defaultdict(collections.Counter)
    for component in storage['components']:
        shape = storage['shapes'][component['shape']]
        if len(component['frames']) != len(shape['programs']):
            raise ValueError('incomplete source wiring')
        if len(component['roots']) != len(shape['signals']):
            raise ValueError('incomplete symbol roots')
        local = [v for v in component['roots'] if v is not None]
        roots.update(local)
        counts['bound_symbols'] += len(local)
        counts['same_component_repeated_roots'] += len(local) - len(set(local))
        distributions['component_width'][len(component['frames'])] += 1
        for ordinal, source in enumerate(component['frames']):
            if source in seen:
                raise ValueError('source has multiple component positions')
            seen.add(source)
            frame = frames.get(source)
            counts['positioned_sources'] += 1
            if frame is None:
                counts['positions_without_source_storage'] += 1
                continue
            counts['stored_positioned_sources'] += 1
            counts['single_source_component_records'] += len(component['frames']) == 1
            counts['completed_source_records'] += frame['completed']
            counts['externally_retained_sources'] += frame['retainers'] > 0
            counts['parented_sources'] += frame['parent'] is not None
            program = storage['programs'][shape['programs'][ordinal]]
            distributions['facts_per_source'][len(frame['facts'])] += 1
            for fact in frame['facts']:
                counts['facts'] += 1
                if not fact['owned']:
                    counts['unowned_facts'] += 1
                    continue
                columns = program['fields'][fact['op']]
                if not columns:
                    raise ValueError('owned fact has no template field wiring')
                counts['owned_facts'] += 1
                counts['hidden_owned_facts'] += fact['hidden']
                scalar_free = all(s is not None for s in columns)
                counts['scalar_free_owned_facts'] += scalar_free
                counts['scalar_bearing_owned_facts'] += not scalar_free
                inherited = fact['born'] == frame['started_epoch'] and fact['epoch'] == frame['started_epoch']
                counts['facts_with_source_lifecycle'] += inherited
                counts['scalar_free_facts_with_source_lifecycle'] += scalar_free and inherited
    counts['distinct_roots'] = len(roots)
    counts['all_repeated_roots'] = counts['bound_symbols'] - len(roots)
    counts['cross_component_repeated_roots'] = counts['all_repeated_roots'] - counts['same_component_repeated_roots']
    counts['source_records_outside_components'] = len(set(frames) - seen)
    fields = dict(snapshot['graph_fields'])
    return dict(counts=dict(counts), distributions={k: dict(sorted(v.items())) for k,v in distributions.items()},
                graph_bytes=snapshot['graph_owned_teardown_bytes'],
                retained_program_bytes=snapshot['retained_program_teardown_bytes'],
                graph_fields=sorted(fields.items(), key=lambda item: -item[1]),
                graph_remaining_even_without_all_cells=snapshot['graph_owned_teardown_bytes']-fields['cells'],
                # A deliberately impossible upper bound: all current duplicates
                # disappear with no replacement address, validity, or lookup cost.
                oracle_duplicate_binding_payload_bytes=16*counts['all_repeated_roots'],
                oracle_payload_scope='64-bit Option<u64> values only; excludes boundary records, capacity and replacement addressing costs')


def analyze(root):
    cases=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        rows=[]
        for variant in ('prefix-all','dual-source-inherited'):
            path=root/variant/case/'dual-shared-memory.json'
            data=path.read_bytes();snapshot=json.loads(data)
            rows.append(dict(variant=variant, snapshot_sha256=hashlib.sha256(data).hexdigest(),
                             program=snapshot['program_sha256'],runs=snapshot['runs'],
                             final=snapshot['final_state_sha256'],**census(snapshot)))
        if rows[0]['runs']!=rows[1]['runs'] or rows[0]['final']!=rows[1]['final']:
            raise ValueError('different workloads or final states')
        cases.append(dict(case=case,lanes=rows))
    return dict(scope='saved standalone Cell CPU final states; structural opportunities and impossible bounds, not proven savings',
                limitations=['Root equality does not prove whole-Cell equivalence or deletion safety.',
                    'Hidden facts and sources without local facts may still serve congruence and external Entries.',
                    'Matching source epochs does not prove a future immutable lifecycle.',
                    'Final state counts are not execution peaks or RHS work counts.',
                    'Template projection already removes some scalar-free records when enabled; do not count it again.'],cases=cases)


if __name__=='__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])),indent=2)+'\n')
