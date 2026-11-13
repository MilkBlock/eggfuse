"""Paired, same-binary memory audit for authoritative Cell scalar fields."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def analyze(root):
    base={c['case']:c for c in read(root/'prefix-all/checked.json')['cases']}
    checked={c['case']:c for c in read(root/'prefix-all/cell-fields-checked.json')['cases']}
    overlap={c['case']:c for c in read(root/'prefix-all/cell-overlap-checked.json')['cases']}
    results=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        paths=[root/'prefix-all'/case/f'source-{mode}-memory.json' for mode in ('template','cell')]
        lanes=[read(p) for p in paths]
        for check in (base[case],checked[case],overlap[case]):
            if not check['all_saved_run_checks_equal']:
                raise ValueError('missing saved-Run acceptance')
            for lane in lanes:
                if (check['program'],check['runs'],check['final_state']) != (lane['program_sha256'],lane['runs'],lane['final_state_sha256']):
                    raise ValueError('memory execution does not match the verified workload')
        if lanes[1]['stable_fields']['materialized_stable_nodes']!=0:
            raise ValueError('new path still retains per-fact stable records')
        if lanes[0]['stable_fields']['stats']['cell_fields'] or not lanes[1]['stable_fields']['stats']['cell_fields']:
            raise ValueError('incorrect ablation modes')
        if lanes[0]['source_storage']['fact_record_live_bytes']!=lanes[1]['source_storage']['fact_record_live_bytes']:
            raise ValueError('field projection unexpectedly changed fact storage')
        memory={k:[m[k] for m in lanes] for k in ['graph_owned_teardown_bytes','retained_program_teardown_bytes','execution_and_takeover_peak_bytes','max_takeover_extra_bytes']}
        results.append(dict(case=case,program=lanes[0]['program_sha256'],runs=lanes[0]['runs'],
            input_hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths],
            saved_run_checks_equal=True,overlap_saved_run_checks_equal=True,
            memory=memory,graph_reduction_percent=100*(1-memory['graph_owned_teardown_bytes'][1]/memory['graph_owned_teardown_bytes'][0]),
            graph_fields={k:[dict(m['graph_fields'])[k] for m in lanes] for k in dict(lanes[0]['graph_fields'])},
            source_storage={k:[m['source_storage'][k] for m in lanes] for k in ['explicit_cell_slots','cell_slot_bytes','completed_owner_frames','fact_record_live_bytes']},
            fields={k:[m['stable_fields'][k] for m in lanes] for k in ['live_stable_nodes','materialized_stable_nodes','template_projected_nodes']},
            scalar_work={k:[m['stable_fields']['stats'][k] for m in lanes] for k in ['cell_scalar_installs','cell_scalar_reads','node_retirement_probes']},
            overlap=overlap[case]['completion_batches']['overlap']))
    return dict(scope='actual standalone Cell CPU; same frozen binary; template-only projection versus Cell scalar ownership; no native or timing claim',cases=results)


if __name__=='__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])),indent=2)+'\n')
