"""Post-execution final-state isomorphism, source schedule and row complementarity."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
from audit import graph


def endpoint(packet,output,reference):
    p=json.loads(packet.read_text());run=json.loads((output/'run.json').read_text())
    ref=json.loads((reference/'state.json').read_text());steps=json.loads((reference/'report.json').read_text())['steps']
    raw_rhs=json.loads((reference/'rhs.json').read_text());raw_writes=json.loads((reference/'writes.json').read_text())
    raw_resume=json.loads((reference/'resumes.json').read_text())
    with np.load(output/'output.npz') as z:
        result=dict(completed=run['completed'],device_done=run['finished'],reference_runs=len(steps))
        active=z['meta'][:,3]!=2
        result.update(device_rows=int(active.sum()),reference_rows=len(ref['rows']))
        try:
            _,match=graph(z['rows'],z['meta'],ref,p,run['strings'],z['parents'])
            result['full_typed_graph_equal']=match
        except (ValueError,KeyError,AssertionError) as exc:
            result.update(full_typed_graph_equal=False,graph_difference=str(exc))
        result['first_schedule_difference']=next((i for i,(s,v) in enumerate(zip(steps,z['runs']),1)
            if run['sets'][v[0]]!=s['ruleset'] or bool(v[3])!=s['changed']),None)
        result['first_rhs_count_difference']=next((i for i,(s,v) in enumerate(zip(steps,z['runs']),1)
            if s['executed_bindings']!=v[1]),None)
        result['first_write_count_difference']=next((i for i,(s,v) in enumerate(zip(raw_writes,z['runs']),1)
            if s[0]!=v[2]),None)
        # All tokens have rule-scoped tuple widths; do not hash padding.
        by_row=[set(),set()];duplicates=0
        for r in z['rhs']:
            rid=int(r[1]);key=(int(r[0]),rid,*map(int,r[4:4+len(p['rules'][rid]['inputs'])]))
            row=int(r[2]);duplicates+=key in by_row[row];by_row[row].add(key)
        result.update(tokens=[len(a) for a in by_row],cross_row_duplicates=len(by_row[0]&by_row[1]),within_row_duplicates=duplicates,
                      first_required_continuation=next((i for i,(count,_) in enumerate(raw_resume,1) if count),None),
                      cpu_continuations=sum(x[0] for x in raw_resume),gpu_continuations=0,
                      measured_inference_ms=run['inference_ms'],measured_cli_work_ms=run['total_ms'])
    result['acceptance']='incomplete'  # Device Spine delivery and all ordered digests are separate mandatory endpoints.
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('packet','gpu','oracle','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(endpoint(a.packet,a.gpu,a.oracle),indent=1)+'\n')
