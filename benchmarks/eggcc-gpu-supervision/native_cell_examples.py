"""Extract local input/target partitions from native synthetic Cell execution.

Eq numbers are local partition evidence, never numeric model features. Output
partitions are labels only. Shared Eq does not prove producer ownership.
"""
import argparse
import json
from pathlib import Path


def partition(ports, field):
    classes={}
    return [classes.setdefault((p['sort'],p[field]),len(classes)) for p in ports]


def extract(trace):
    if not trace.get('relations') or not trace.get('all_slots'):
        raise ValueError('capture requires --relations')
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):
        raise ValueError('native audit failed')
    examples=[]
    for run in trace['runs']:
        for ordinal,row in enumerate(run['audit']['bindings']):
            if not row['rhs']['completed']:
                raise ValueError('incomplete RHS')
            ports=sorted(row['eq_ports'],key=lambda p:p['slot'])
            values=sorted(row['values'],key=lambda p:p['slot'])
            if {p['slot'] for p in ports}!={v['slot'] for v in values if 'eq' in v['value']}:
                raise ValueError('incomplete input partition')
            rhs=sorted(row['rhs']['slots'],key=lambda p:p['slot'])
            if any('unavailable' in v for v in rhs):
                raise ValueError('unavailable RHS slot')
            outputs=[dict(v['eq_port'],slot=v['slot']) for v in rhs if 'eq_port' in v]
            examples.append(dict(
                address=dict(run=run['ordinal'],binding=ordinal,rule=row['rule']),
                inputs=dict(eq_slots=[p['slot'] for p in ports],
                            eq_partition=partition(ports,'before'),
                            scalars=[v for v in values if 'eq' not in v['value']]),
                targets=dict(input_partition=partition(ports,'after'),
                             rhs_eq_slots=[p['slot'] for p in outputs],
                             rhs_partition=partition(outputs,'after_run'),
                             rhs_scalars=[v for v in rhs if 'eq_port' not in v]),
                ownership='unobserved'))
    return dict(schema='native-cell-partitions/v1',program_sha256=trace['program_sha256'],
                scope='actual native local input features and post-Run targets; no inferred ownership',
                templates=trace['recipe']['rules'],examples=examples)


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    out=extract(json.loads(a.trace.read_text()));a.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(examples=len(out['examples']),program_sha256=out['program_sha256'])))
if __name__=='__main__':main()
