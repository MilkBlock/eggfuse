#!/usr/bin/env python3
"""Summarize actual witness routes without treating observations as proofs."""
import collections
import json
import sys
from pathlib import Path

def collect(root):
    report=json.loads((root/'checked.json').read_text())
    rows=[]
    for case in report['cases']:
        if case['all_saved_run_checks_equal'] is not True:raise ValueError('unaudited trace')
        raw=json.loads((root/case['case']/'candidate.json').read_text())
        if case['program']!=raw['sha256']:raise ValueError('program mismatch')
        saturation=case['catalog_trace']['saturation']
        groups=collections.defaultdict(list)
        ranked=[]
        for path in saturation['witness_paths']:
            rule=raw['recipe']['rules'][path['rule']]
            for op,frame,source_op in path['constructor_positions']:
                if rule['effects'][op].get('kind')!='construct':raise ValueError('not a constructor')
                if frame<0 or source_op<0:raise ValueError('negative position')
            groups[path['rule'],path['shape']].append(path)
            ranked.append(dict(path,rule_name=rule['metadata']['name'],ruleset=rule['metadata']['source_set']))
        ranked.sort(key=lambda p:-p['applications']*len(p['constructor_positions']))
        rows.append(dict(case=case['case'],program=case['program'],runs=case['runs'],
            all_saved_run_checks_equal=True,paths=len(ranked),rule_shape_groups=len(groups),
            multi_path_groups=sum(len(v)>1 for v in groups.values()),
            applications=sum(p['applications'] for p in ranked),
            constructor_positions_weighted=sum(p['applications']*len(p['constructor_positions']) for p in ranked),
            ranked_paths=ranked))
    if sum(r['runs'] for r in rows)!=2652:raise ValueError('missing Runs')
    return dict(scope='Observed shape-relative RHS constructor witnesses; not a static proof or saved-work claim',cases=rows)
if __name__=='__main__':
    d=collect(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(d,indent=2)+'\n')
    for row in d['cases']:print({k:v for k,v in row.items() if k!='ranked_paths'})
