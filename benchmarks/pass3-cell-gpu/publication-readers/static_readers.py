"""Count actual declared Entry readers and conservative future-schedule regions."""
import json
from pathlib import Path


def describe(path):
    p=json.loads(Path(path).read_bytes());r=p['recipe'];nodes=p['entry_schedule']['nodes']
    shared={c['rule'] for node in nodes for c in node['consumers']}
    read_tables={rid:{atom['call']['table'] for atom in rule['query'] if 'table' in atom['call']} for rid,rule in enumerate(r['rules'])}
    pending_only={rid:sorted(tables) for rid,tables in read_tables.items() if rid not in shared and tables}
    def leaves(v):
        if 'run' in v:return {v['run']}
        if 'sequence' in v:return set().union(*(leaves(i) for i in v['sequence']))
        if 'repeat' in v:return leaves(v['body']) if v['repeat'] else set()
        return leaves(v['saturate'])
    regions=[]
    def visit(v):
        if 'sequence' in v:
            for x in v['sequence']:visit(x)
        elif 'repeat' in v and v['repeat']==1:visit(v['body'])
        elif leaves(v):regions.append(sorted(leaves(v)))
    for v in r['control']:visit(v)
    last={};sets={s['name']:s['rule_ids'] for s in r['rulesets']}
    for i,names in enumerate(regions):
        for name in names:
            for rid in sets[name]:last[rid]=i
    return dict(rules=len(r['rules']),tables=len(r['tables']),entry_nodes=len(nodes),
             entry_rules=len(shared),uncovered_rule_ids=sorted(set(read_tables)-shared),
             native_pending_table_readers=pending_only,
             source_table_reader_links=sum(len(t) for t in read_tables.values()),
             outer_regions=regions,last_static_region_counts=[sum(x==i for x in last.values()) for i in range(len(regions))])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('program',type=Path);parser.add_argument('out',type=Path)
    a=parser.parse_args();a.out.write_text(json.dumps(describe(a.program),indent=1)+'\n')
