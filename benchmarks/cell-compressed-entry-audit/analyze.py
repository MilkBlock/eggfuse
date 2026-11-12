"""Read saved structural-compression artifacts; no runtime or benchmark rerun."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    for name in ('baseline','trace','program','profile','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    data={name:json.loads(getattr(args,name).read_text()) for name in ('baseline','trace','program','profile')}
    base,trace,program,profile=(data[k] for k in ('baseline','trace','program','profile'))
    if base['run_checks']!=trace['run_checks']:raise ValueError('original Run boundaries/audits differ')
    if not trace['every_run_graph_and_ordered_audits_equal']:raise ValueError('comparison failed')
    source=base['program_sha256']
    if not source==trace['program_sha256']==profile['source']==program['ownership_fragments']['source']:
        raise ValueError('unrelated source artifacts')
    if program['ownership_markers']['recipe']!=program['recipe']['sha256']:raise ValueError('recipe mismatch')
    plan=program['ownership_markers']['plan']
    summary=trace['ownership']['plan_summary']
    if (summary['port_programs']!=len(plan['programs'])
        or summary['fragments']!=len(plan['composition']['transitions'])
        or summary['max_frames']!=plan['composition']['max_frames']):
        raise ValueError('compiled plan dimensions differ from recorded runtime plan')
    templates=collections.Counter();programs=collections.Counter();kinds=collections.Counter()
    delegated=0;nonowned=0;slots=0;factless=0
    for identity,cell in trace['instance_trace']:
        tid=cell['template'];templates[tid]+=1;delegated+=bool(cell.get('symbolic_slots'))
        factless+=not bool(cell['facts'])
        slots+=len(cell['values']);kinds.update(next(iter(v)) for v in cell['values'].values())
        marker=plan['markers'][tid]
        if marker['active']:programs[marker['program_id']]+=1
        else:nonowned+=1
    static=[]
    for pid,count in sorted(programs.items()):
        code=plan['programs'][pid]
        static.append(dict(program=pid,retained_instances=count,
                           field_positions=sum(len(row) for row in code['fields']),
                           equality_field_positions=sum(v is not None for row in code['fields'] for v in row),
                           scalar_field_positions=sum(v is None for row in code['fields'] for v in row)))
    original=base['graph_owned_heap_requested_before'];after=trace['graph_owned_heap_requested_after']
    extra=trace['ownership']['inventory']['shared_field_layout_bytes']
    result=dict(scope='Read-only actual-runtime snapshot audit, not new performance or training accuracy',
                source_program=source,baked_program=program['sha256'],runs=trace['runs'],run_checks_equal=True,
                saved_measurement=dict(original_graph_bytes=original,compressed_graph_bytes=after,
                                       added_shared_layout_bytes=extra,combined_fraction=(after+extra)/original,
                                       excludes='complete Program/Executor heap and within-Run peaks'),
                retained=dict(instances=len(trace['instance_trace']),templates=len(templates),
                              active_port_programs=len(programs),inactive_marker_instances=nonowned,
                              delegated_frames=delegated,explicit_slots=slots,slot_kinds=dict(kinds),factless_frames=factless),
                compiled=dict(port_programs=len(plan['programs']),fragment_recipes=len(program['ownership_fragments']['fragments']),
                              checked_transitions=len(plan['composition']['transitions']),
                              observed_profile_candidates=len(profile['records'])),
                static_field_work_proxy=dict(per_instance=sum(r['field_positions']*r['retained_instances'] for r in static),
                                            once_per_used_program=sum(r['field_positions'] for r in static),
                                            meaning='static field visits only; not inference speedup, bytes, or all dynamic equality checks'),
                used_programs=static,
                missing_for_learning=['time-aligned component/frame-to-symbol maps and bound signal values',
                                      'available boundary conditions and observations before completion',
                                      'exact complete-target equivalence and derivation certificate',
                                      'retirement/visibility metadata aligned with each example'],
                warning='Final delegated slots are intentionally absent: never treat missing slots as zero or unknown input labels. Aggregate profile counts are not completion labels.',
                provenance_limit='Source hashes and plan dimensions agree; saved trace does not record the optimized Program hash, so exact optimized-artifact identity is not independently established.',
                fingerprints={name:hashlib.sha256(getattr(args,name).read_bytes()).hexdigest() for name in data})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('used_programs','fingerprints')},indent=2))


if __name__=='__main__':main()
