"""Run one memory lane against frozen controls; no timing or native proof."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(before, after):
    for key in ('program_sha256', 'runs', 'final_state_sha256'):
        if before[key] != after[key]:
            raise ValueError('state mismatch: ' + key)
    # These inventories carry fact identity, membership, lifecycle, source
    # retention and exact static wiring. Array layout/hash payloads may differ.
    for category, field in [('source_storage', 'fact_lifecycle'),
                            ('ownership_storage', 'components'),
                            ('ownership_storage', 'shapes')]:
        if before[category][field] != after[category][field]:
            raise ValueError('inventory mismatch: ' + field)
    a=before['source_storage']['completed_owners']
    b=after['source_storage']['completed_owners']
    old_hash_bytes=a.get('stored_hash_bytes', a['stored_fact_entries']*8)
    field_deltas={k: value-dict(before['graph_fields'])[k] for k,value in after['graph_fields']
                  if value!=dict(before['graph_fields'])[k]}
    return dict(graph_field_deltas=field_deltas, runs=after['runs'], final_state_sha256=after['final_state_sha256'],
        graph_before=before['graph_owned_teardown_bytes'],
        graph_after=after['graph_owned_teardown_bytes'],
        graph_saved=before['graph_owned_teardown_bytes']-after['graph_owned_teardown_bytes'],
        hash_before=old_hash_bytes, hash_after=b['stored_hash_bytes'],
        hash_saved=old_hash_bytes-b['stored_hash_bytes'],
        takeover_extra_before=before['max_takeover_extra_bytes'],
        takeover_extra_after=after['max_takeover_extra_bytes'],
        process_peak_before=before['execution_and_takeover_peak_bytes'],
        process_peak_after=after['execution_and_takeover_peak_bytes'],
        retained_program_before=before['retained_program_teardown_bytes'],
        retained_program_after=after['retained_program_teardown_bytes'],
        matched_inventories=True)


def main(binary, saved, programs, output, report):
    output.mkdir(exist_ok=False, parents=True)
    frozen=output/'runtime_storage_peak'
    shutil.copy2(binary, frozen)
    rows=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        source=programs/case/'candidate.json'
        target=output/(case+'.json')
        subprocess.run([str(frozen.resolve()),str(source.resolve()),str(target.resolve()),
                        'inherited-owners','--port-domains-only','--cell-fields'],
                       check=True, stdout=subprocess.DEVNULL)
        control=saved/(case+'.json')
        row=dict(case=case, control_sha256=digest(control), candidate_sha256=digest(target),
                 **compare(json.loads(control.read_text()),json.loads(target.read_text())))
        rows.append(row)
        print(case, row['graph_before'], '->',row['graph_after'], 'hash saved',row['hash_saved'],flush=True)
    result=dict(scope='standalone Cell CPU; frozen b3322f9f observations versus current branch, cumulative changes, not an isolated hash ablation',
        candidate_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        candidate_binary_sha256=digest(frozen),
        limitations=['Final state and retained inventories match; not per-Run semantic acceptance.',
            'Process high-water includes retained Program and is not a Graph-only peak.',
            'Historical control has dense eight-byte hashes per stored fact position.',
            'No native egglog acceptance or latency measurement.'],cases=rows)
    report.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main(*(Path(arg) for arg in sys.argv[1:]))
