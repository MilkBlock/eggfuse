"""Compile verified old/new merge constructors and their correlated two-table consumers."""
import argparse
import json
from pathlib import Path


def plan(program):
    source=json.loads(program.read_bytes())['recipe'];tables=source['tables'];names={t['name']:i for i,t in enumerate(tables)}
    merges={}
    for t,v in enumerate(tables):
        exp=v.get('merge_expr') or {};output=exp.get('call',{}).get('table')
        if output in names and exp.get('args')==[{'var':'old'},{'var':'new'}]:merges[t]=names[output]
    rules=source['rules'];routes=[]
    for parent,r in enumerate(rules):
        for effect,op in enumerate(r['effects']):
            if op['op']!='set':continue
            t=names[op['call']['table']]
            if t not in merges or 'slot' not in op['value']:continue
            s=op['value']['slot'];ctor=next(((i,names[x['call']['table']]) for i,x in enumerate(r['effects'][:effect]) if x['op']=='let' and x.get('dst')==s and 'table' in x['call']),None)
            if not ctor:continue
            site,parent_table=ctor;merge_table=merges[t]
            for consumer,child in enumerate(rules):
                if len(child['query'])!=2:continue
                for m,q in enumerate(child['query']):
                    other=child['query'][1-m]
                    if q['call'].get('table')!=tables[merge_table]['name'] or other['call'].get('table')!=tables[parent_table]['name']:continue
                    if len(q['args'])!=3 or q['args'][1]!=other['args'][-1]:continue
                    routes.append([parent,effect,t,site,parent_table,merge_table,consumer,m])
    return routes


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('program',type=Path);a.add_argument('out',type=Path);args=a.parse_args()
    args.out.write_text(json.dumps(plan(args.program)))
