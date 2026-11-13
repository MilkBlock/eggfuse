#!/usr/bin/env python3
"""Pair same-program executions; count actual teardown savings, not logical facts."""
import json
import sys
from pathlib import Path

def collect(before, after):
    rows=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        a=json.loads((before/(case+'.json')).read_text())
        b=json.loads((after/(case+'.json')).read_text())
        for key in ('program_sha256','runs','final_state_sha256','completion_work','source_storage'):
            if a[key]!=b[key]: raise ValueError(f'{case}: changed {key}')
        af,bf=dict(a['graph_fields']),dict(b['graph_fields'])
        changes={k:[af.get(k,0),bf.get(k,0)] for k in af.keys()|bf.keys() if af.get(k,0)!=bf.get(k,0)}
        if set(changes)!={'ownership.barriers'} or bf['ownership.barriers']!=0:
            raise ValueError(f'{case}: unexpected storage changes {changes}')
        old,new=a['graph_owned_teardown_bytes'],b['graph_owned_teardown_bytes']
        if old-new!=af['ownership.barriers']: raise ValueError('teardown delta')
        rows.append(dict(case=case,program=b['program_sha256'],runs=b['runs'],
            before_bytes=old,after_bytes=new,saved_bytes=old-new,saved_fraction=(old-new)/old,
            exact_final_state_and_work=True,only_changed_field=changes))
    return dict(scope='Standalone Cell CPU Graph owned heap; observation storage removal, no logical fact reduction or timing claim',cases=rows)

if __name__=='__main__':
    result=collect(Path(sys.argv[1]),Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n')
    for row in result['cases']: print(row['case'],row['saved_bytes'],row['saved_fraction'])
