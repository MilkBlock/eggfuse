"""Lower constructor sites within Cell effect order; leave other work explicit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from collect_observed_corpus import read_bytes


def compile_sites(recipe):
    tables={t['name']:(i,t) for i,t in enumerate(recipe['tables'])}
    sites=[];marks=[];prefixes=[]
    for rid,rule in enumerate(recipe['rules']):
        prefix=0;blocked=False
        for oi,op in enumerate(rule['effects']):
            reason=None
            table=tables.get(op.get('call',{}).get('table'))
            if op['kind']!='construct':reason='effect:'+op['kind']
            elif table is None or table[1]['kind']!='constructor':reason='not_immutable_constructor'
            elif any('slot' not in a for a in op['args']):reason='literal_argument'
            if reason:
                marks.append(dict(rule=rid,operation=oi,reason=reason));blocked=True;continue
            args=[a['slot'] for a in op['args']]
            if any(not 0<=s<len(rule['slots']) for s in [*args,op['dst']]):raise ValueError('invalid source slot')
            sites.append(dict(rule=rid,operation=oi,table=table[0],args=args,dst=op['dst'],last_effect=oi==len(rule['effects'])-1))
            if not blocked:prefix+=1
        prefixes.append(prefix)
    return dict(sites=sites,marks=marks,prefixes=prefixes,
        fully_constructor_rules=[i for i,(p,r) in enumerate(zip(prefixes,recipe['rules'])) if p and p==len(r['effects'])])


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.source);recipe=json.loads(raw)['recipe'];plan=compile_sites(recipe)
    result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),rules=len(recipe['rules']),compiled_sites=len(plan['sites']),
        initially_reachable_sites=sum(plan['prefixes']),rules_with_constructor_prefix=sum(p>0 for p in plan['prefixes']),
        fully_constructor_rules=plan['fully_constructor_rules'],boundary_counts=dict(Counter(m['reason'] for m in plan['marks'])),
        scope='Static lowering counts, not executed matches or committed mutations',
        witness_snapshot_required=True,global_namespace_required=True,union_supported=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
