"""Migration check: native generated source vs independent local reference.

Private seed constructors anchor input Eq ports; only those declared seed rows
are excluded from graph comparison. Not a full Eggcc benchmark acceptance rule.
"""
import argparse,json
from pathlib import Path
from synthetic_cell_inputs import validate
from synthetic_native_source import emit
from device_snapshot_import import identity
from reference_union_family import Reference
from reference_family_schedule import execute


def compare(document,trace,schedule):
    recipe,snapshot=validate(document);ids={};ports=[]
    for row in snapshot['rows']:
        for v in row['values']:
            ids.setdefault(identity(v),len(ids))
            if 'eq' in v and v not in ports:ports.append(v)
    ref=Reference(recipe,snapshot['rows'],ids);runs=execute(ref,schedule)
    expected=ref.normalized_facts();lookup={(t,vs[:-1]):vs[-1] for t,vs in expected};mapping={};errors=[]
    def bind(value,wanted):
        key=identity(value)
        if key in mapping and mapping[key]!=wanted:errors.append('inconsistent_class')
        else:mapping[key]=wanted
    seeds={'SyntheticSeed_'+v['sort'] for v in ports};facts=[];seen=set()
    for row in trace['final']['rows']:
        if row['subsumed']:raise ValueError('hidden native row')
        if row['table'] in seeds:
            index=row['values'][0]['value']
            if type(index)is not int or not 0<=index<len(ports) or row['table']!='SyntheticSeed_'+ports[index]['sort']:raise ValueError('invalid seed anchor')
            bind(row['values'][-1],ref.root(ids[identity(ports[index])])) ;seen.add(index)
        else:facts.append(row)
        for v in row['values']:
            if 'eq' not in v and identity(v) in ref.scalar_ids:bind(v,ref.scalar_ids[identity(v)])
    if seen!=set(range(len(ports))):errors.append('missing_seed_anchor')
    pending=facts[:]
    for _ in range(len(facts)+1):
        todo=[];progress=False
        for row in pending:
            args=[identity(v) for v in row['values'][:-1]]
            if any(k not in mapping for k in args):todo.append(row);continue
            key=(row['table'],tuple(mapping[k] for k in args))
            if key not in lookup:errors.append('unexpected_fact');continue
            result=row['values'][-1];progress|=identity(result) not in mapping;bind(result,lookup[key])
        pending=todo
        if not pending or not progress:break
    if pending:errors.append('unresolved_fact')
    actual={(row['table'],tuple(mapping[identity(v)] for v in row['values'])) for row in facts if all(identity(v) in mapping for v in row['values'])}
    if actual!=expected:errors.append('fact_difference')
    if len(set(mapping.values()))!=len(mapping):errors.append('missing_union')
    audited=all(trace.get(k)is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal'))
    return dict(passed=audited and not errors,errors=errors,native_audits=audited,expected_facts=len(expected),native_projected_facts=len(actual),seed_anchors=len(seen),reference_runs=len(runs),native_runs=len(trace['runs']))


def main():
    p=argparse.ArgumentParser()
    for k in ['input','trace','source','output']:p.add_argument(k,type=Path)
    p.add_argument('--schedule',type=Path);a=p.parse_args();d=json.loads(a.input.read_text());t=json.loads(a.trace.read_text())
    stages=list(dict.fromkeys(r['metadata']['source_set'] for r in d['recipe']['rules']))
    if not a.schedule and len(stages)!=1:raise ValueError('schedule required')
    schedule=json.loads(a.schedule.read_text()) if a.schedule else dict(saturate=dict(run=stages[0]))
    if a.source.read_text()!=emit(d,schedule):raise ValueError('source replay mismatch')
    out=compare(d,t,schedule);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
    if not out['passed']:raise SystemExit(1)
if __name__=='__main__':main()
