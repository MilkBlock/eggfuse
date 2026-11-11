#!/usr/bin/env python3
"""Check saved flat-dispatch results against the reviewed grouped control."""
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name('collect.py')))
read, sha, signature = (helpers[k] for k in ('read','sha','signature'))


def collect(root, output):
    prior = read(Path(__file__).with_name('results.json'))
    result = {'baseline_commit':'4abd900b',
        'scope':'standalone Cell CPU; saved work and relative state checks, no timing',
        'binary_sha256':sha(root/'runtime-final'), 'cases':{}}
    for case in ('sum','ray1280','ray-full'):
        before = root.parent/'cell-column-influence'/(case+'-grouped')
        after = root/(case+'-final')
        assert sha(before/'report.json')==prior['cases'][case]['report_sha256'][1]
        a,b=[read(p/'report.json') for p in (before,after)]
        assert sha(before/'state.json')==sha(after/'state.json')
        assert signature(a)==signature(b)
        for key in ('stats','indexed_columns','entry_schedule','free_join','key_lookup_calls',
                    'prefix_configuration','program_sha256','publication'):
            assert a[key]==b[key],(case,key)
        old,new=[r['sieve'].copy() for r in (a,b)]
        assert old.pop('column_influence')=='cell-fields/v1'
        assert new.pop('column_influence')=='cell-fields/v2'
        payload=[s.pop('influence_payload_bytes') for s in (old,new)]
        work=[s.pop('stats').copy() for s in (old,new)]
        checks=[s.pop('column_checks') for s in work]
        dispatches=work[1].pop('publication_dispatches')
        inactive=work[1].pop('inactive_publications')
        assert old==new and work[0]==work[1]
        result['cases'][case]={
            'state_sha256':sha(after/'state.json'),'ordered_run_sha256':signature(b),
            'reports_sha256':[sha(p/'report.json') for p in (before,after)],
            'column_checks':checks,'publication_dispatches':dispatches,
            'inactive_publications':inactive,'influence_payload_bytes':payload,
            'summary_update_rows':b['sieve']['stats']['update_rows'],
            'unchanged_column_rows':b['sieve']['stats']['unchanged_column_rows'],
            'equal_weight_dispatch_and_check_delta':checks[1]+dispatches-checks[0],
            'exact_state_ordered_runs_and_remaining_work':True,
        }
    assert read(root/'semantic-acceptance.json')['status']=='pass'
    assert sha(root/'semantic/run-values/state.json')==result['cases']['sum']['state_sha256']
    result['sum_native_acceptance_sha256']=sha(root/'semantic-acceptance.json')
    output.write_text(helpers['json'].dumps(result,indent=2)+'\n')
    print({case:(r['column_checks'],r['publication_dispatches'],r['inactive_publications']) for case,r in result['cases'].items()})


if __name__=='__main__':
    if not __debug__: raise SystemExit('run without -O')
    collect(Path(sys.argv[1]),Path(sys.argv[2]))
