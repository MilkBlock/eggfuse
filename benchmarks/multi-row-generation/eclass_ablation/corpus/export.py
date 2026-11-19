"""Admit positive port certificates only after matching source and actual Run witnesses."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from replays import HERE, RULES


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(condition, description):
    if not condition:raise ValueError(description)


def term_values(graph):
    observed={};seen=set()
    for row in graph['rows']:
        if row['subsumed']:continue
        values=row['values']
        if row['table']=='Observe':observed[values[0]['value']]=values[1]['eq']
        if row['table']=='Seen':seen.add((values[0]['value'],values[1]['value']))
    return observed,seen


def typed_body(rule):
    return [rule['query'],rule['effects'],[(s['sort'],s['definition']) for s in rule['slots']]]


def check(case, source_rule):
    meta=case['metadata']; count=len(meta['ports']); lhs,rhs=meta['pair']; active=meta['committed'] and meta['guard']
    selected=[r for r in case['compiled_program']['recipe']['rules'] if r['metadata']['source_set']==source_rule['metadata']['source_set']]
    if selected or meta['committed']:
        require(len(selected)==1 and typed_body(selected[0])==typed_body(source_rule), 'fixture changes the typed source body')
    require(source_rule['metadata']['name'] in case['source'],'missing frozen source rule')
    require(len(case['steps'])==3 and [s['ruleset'] for s in case['steps']]==['observe',source_rule['metadata']['source_set'] if meta['committed'] else 'withheld','observe'],'unexpected schedule')
    require(case['steps'][1]['logical_matches']==(2 if active else 0), 'wrong producer match count')
    initial, seen0=term_values(case['initial']);before, observed0=term_values(case['boundaries'][0]['graph']);after,_=term_values(case['boundaries'][1]['graph']);final,observed1=term_values(case['boundaries'][2]['graph'])
    require(initial==before and after==final and not seen0 and len(before)==count*2,'missing or changed probe handles')
    expected=set()
    for a in before:
        for b in before:
            if before[a]==before[b] or (active and a//16==b//16 and {a%16,b%16}=={lhs,rhs}): expected.add((a,b))
    actual={(a,b) for a in after for b in after if after[a]==after[b]}
    require(expected==actual,'full partition changed outside certified slot pair')
    for obs,values in ((observed0,before),(observed1,after)):
        expected_observed={(a,j) for a in values for j in range(2) if values[a]==values[16*j+rhs]}
        require(obs==expected_observed, 'next Run did not observe the expected port partition')
    independent=[i for i in range(count) if i not in (lhs,rhs) and len({before[x] for x in (lhs,rhs,i,16+lhs,16+rhs,16+i)})==6]
    return dict(id=case['id'],pre_sort_partition=sorted([sorted([p for p,v in before.items() if v==value]) for value in set(before.values())]),
                post_sort_partition=sorted([sorted([p for p,v in after.items() if v==value]) for value in set(after.values())]),
                producer_matches=case['steps'][1]['logical_matches'], pre_reads=sorted(observed0),post_reads=sorted(observed1),
                source_sha256=case['source_sha256'],program_sha256=case['program_sha256'], independent_distractors=independent)


def syntax_graph(rule,metadata):
    nodes=[];edges=[]
    def node(kind,sort='none',ordinal=0):
        i=len(nodes);nodes.append(dict(kind=kind,sort=sort,ordinal=ordinal));return i
    def edge(src,rel,dst):edges.append([src,rel,dst])
    slot_nodes=[node('slot',s['sort']['kind']) for s in rule['slots']]
    root=node('template'); prior_effect=None
    for stage,sequence in (('query',rule['query']),('effect',rule['effects'])):
        for i,op in enumerate(sequence):
            call=node('match' if stage=='query' else op['kind'],ordinal=i);edge(root,stage,call)
            if stage=='effect':
                if prior_effect is not None:edge(prior_effect,'precedes',call)
                prior_effect=call
            # Query arguments are bindings in a previously observed constructor.
            for j,a in enumerate(op.get('args',[op['arg']] if 'arg' in op else [])):
                operand=slot_nodes[a['slot']] if 'slot' in a else node('literal',a['sort']['kind'])
                port=node('query_column' if stage=='query' else 'operand',ordinal=j);edge(operand,'binds',port);edge(port,'input',call)
            if 'dst' in op:edge(call,'defines',slot_nodes[op['dst']])
    ports=[]
    for desc in metadata['ports']:
        i=desc['slot'];n=node('public_port',rule['slots'][i]['sort']['kind'])
        # Terms / handles appear in the evidence. The graph contains only static provenance.
        for j in desc['also_slots']:edge(slot_nodes[j],'projects',n)
        ports.append(dict(slot=i,node=n,sort=desc['sort'],also_slots=desc['also_slots']))
    return dict(nodes=nodes,edges=edges),ports


def group_key(graph):
    # A WL collision conservatively groups additional rule shapes. Sorts, source
    # and operator/table names, port numbers and argument positions are removed.
    nodes=graph['nodes'];adj=[[] for _ in nodes]
    for a,r,b in graph['edges']:
        adj[a].append(('out',r,b));adj[b].append(('in',r,a))
    colors=[digest(n['kind']) for n in nodes]
    for _ in range(12):colors=[digest((c,sorted((d,r,colors[j]) for d,r,j in a))) for c,a in zip(colors,adj)]
    return 'family-'+digest(sorted(colors))[:16]


def main():
    p=argparse.ArgumentParser();p.add_argument('sum_program',type=Path);p.add_argument('ray_program',type=Path);p.add_argument('replays',type=Path);args=p.parse_args()
    programs={label:json.loads(src.read_text()) for label,src in [('sum-bits',args.sum_program),('raytrace',args.ray_program)]}
    # Reuse previous iteration's provenance without assuming independently equal numeric IDs denote equal rules.
    baked=json.loads((HERE.parents[1]/'port_ablation/corpus/manifest.json').read_text());cases=json.loads(args.replays.read_text())['cases'];samples={};evidence=[];excluded=[]
    for case in cases:
        meta=case['metadata'];rid=meta['rule'];rule=programs['sum-bits']['recipe']['rules'][rid];record=check(case,rule);evidence.append(record)
        if not(meta['guard'] and meta['committed']):continue
        graph,ports=syntax_graph(rule,meta);lhs,rhs=meta['pair'];op_id=meta['operation'];third=record['independent_distractors']
        if not third:
            excluded.append(dict(rule=rid,ports=len(ports),reason='no third same-sort port independent across both actual instances'));continue
        provenance={}
        for workload,program in programs.items():
            matches=[i for i,r in enumerate(program['recipe']['rules']) if r['metadata']['name']==rule['metadata']['name'] and typed_body(r)==typed_body(rule)]
            require(len(matches)==1, 'cross-workload provenance missing or ambiguous');i=matches[0]
            producers=sorted({prov['unit'] for t in baked['templates'] for prov in t['provenance'] if prov['catalog']==workload and prov['source_rule']==i});consumers=sorted({prov['unit'] for t in baked['templates'] for prov in t['provenance'] if prov['catalog']==workload and prov['consumer_rule']==i});leaves=[idx for idx,leaf in enumerate(program['spine_blocks']['entries']) if leaf['consumer']==i]
            provenance[workload]=dict(rule=i,recipe_sha256=program['recipe']['sha256'],producer_units=producers,consumer_units=consumers,spine_leaves=leaves)
        local_ops=rule['effects'];raw_slots=[v['slot'] for v in local_ops[op_id]['args']]
        require(local_ops[op_id]['kind']=='union' and len(raw_slots)==2,'missing direct union instruction')
        require(raw_slots[0] in ports[lhs]['also_slots'] and raw_slots[1] in ports[rhs]['also_slots'] and ports[lhs]['sort']==ports[rhs]['sort'],'certificate does not bind operands')
        samples[rid]=dict(id=f'rule-{rid}',family_id=group_key(graph),version=digest(typed_body(rule)),source_sha256=hashlib.sha256(rule['metadata']['name'].encode()).hexdigest(),
                          source=rule['metadata']['name'],provenance=provenance,ports=ports,public_ports=sorted([lhs,rhs,third[0]]),graph=graph,
                          certificates=[dict(left_port=lhs,right_port=rhs,sort=ports[lhs]['sort'],operation=op_id,visible_from_stage=1,guard='producer_committed',scope='template_local',raw_union_slots=raw_slots)])
    # Baked sibling-result proof and a multi-atom query/result alias are held out.
    # Whole color-refinement groups move together even when operand order changes.
    held={samples[r]['family_id'] for r in (143,134)}
    for t in samples.values():t['split']='heldout' if t['family_id'] in held else 'train'
    result=dict(schema='eggfuse.eclass.certified-local-ports/v1',templates=list(samples.values()),excluded=excluded)
    (HERE/'manifest.json').write_text(json.dumps(result,indent=1)+'\n');(HERE/'replay-evidence.json').write_text(json.dumps(evidence,indent=1)+'\n')
    print([(t['id'],t['split'],t['public_ports']) for t in samples.values()]);print('families',len({t['family_id'] for t in samples.values()}),'CPU cases',len(evidence))


if __name__=='__main__':main()
