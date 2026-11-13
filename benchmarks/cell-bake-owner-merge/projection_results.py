#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def collect(root):
    rows=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        a,b=[json.loads((root/f'{case}-{mode}.json').read_text()) for mode in ('materialized','projected')]
        for key in ('program_sha256','runs','final_state_sha256','completion_work','source_storage'):
            if a[key]!=b[key]:raise ValueError(f'{case}: changed {key}')
        pa,pb=a['port_index'],b['port_index']
        if pa['live_stable_nodes']!=pb['live_stable_nodes']:raise ValueError('live fact loss')
        if pb['template_projected_nodes']<=0:raise ValueError('no projection')
        af,bf=dict(a['graph_fields']),dict(b['graph_fields'])
        changes={k:[af.get(k,0),bf.get(k,0)] for k in af.keys()|bf.keys() if af.get(k,0)!=bf.get(k,0)}
        if set(changes)!={'stable_ports'}:raise ValueError(f'unexpected changes {changes}')
        old,new=a['graph_owned_teardown_bytes'],b['graph_owned_teardown_bytes']
        rows.append(dict(case=case,program=b['program_sha256'],runs=b['runs'],before_bytes=old,after_bytes=new,
            saved_bytes=old-new,saved_fraction=(old-new)/old,projected_records=pb['template_projected_nodes'],
            materialized_records=pb['materialized_stable_nodes'],
            template_node_projections=pb['stats']['template_node_projections'],
            field_layout_reads_before=pa['stats']['field_layout_reads'],field_layout_reads_after=pb['stats']['field_layout_reads'],
            changed_fields=changes,exact_final_state_source_storage_and_completion_work=True))
    return dict(scope='Standalone Cell CPU, opt-in template projection, no latency claim',cases=rows)
if __name__=='__main__':
    result=collect(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
    for row in result['cases']:print(row['case'],row['saved_bytes'],row['saved_fraction'])
