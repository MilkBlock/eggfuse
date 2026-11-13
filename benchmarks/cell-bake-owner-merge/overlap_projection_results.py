#!/usr/bin/env python3
"""Preserve Run validation and actual overlap coverage separately."""
import json
import sys
from pathlib import Path

def collect(source):
    raw=json.loads(source.read_text())
    rows=[]
    for row in raw['cases']:
        if row['all_saved_run_checks_equal'] is not True:raise ValueError('Run check failure')
        report=row['completion_batches']
        stats=report['overlap']['stats']
        if not report['enabled'] or not report['overlap']['enabled']:raise ValueError('mode disabled')
        rows.append(dict(case=row['case'],program=row['program'],runs=row['runs'],
            final_state=row['final_state'],all_saved_run_checks_equal=True,
            overlap_exercised=stats['epochs']>0,
            projected_snapshot_exercised=stats['projection_records']>0,
            overlap=report['overlap'],batch_work=report['stats'],
            projected_live_records=row['stable_ports']['template_projected_nodes']))
    if sum(r['runs'] for r in rows)!=2652:raise ValueError('incomplete suite')
    return dict(scope='Standalone differential Run checks; no latency or whole-heap claim',cases=rows)

if __name__=='__main__':
    result=collect(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
    for row in result['cases']:
        print(row['case'],row['overlap_exercised'],row['overlap']['stats'])
