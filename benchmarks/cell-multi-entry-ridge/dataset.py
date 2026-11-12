"""Exact DAG e-class canonicalization and nonduplicate entry-structure splits."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

TABLES={'Input','Get','Single','SubTuple','Concat'}


def canonical(graph):
    by_output=collections.defaultdict(list)
    for row in graph['rows']:
        if row['table'] not in TABLES or row['subsumed']:
            raise ValueError('unsupported table/visibility; do not silently discard facts')
        output=row['values'][-1]
        assert output['sort']=='Expr' and 'eq' in output
        by_output[output['eq']].append(row)
    todo=set(by_output);mapping={};nodes=[]
    while todo:
        ready=[]
        for node in todo:
            facts=[]
            for row in by_output[node]:
                args=[]
                for v in row['values'][:-1]:
                    if 'eq' in v:
                        if v['eq'] not in mapping:break
                        args.append(['eq',v['sort'],mapping[v['eq']]])
                    else:args.append(['literal',v['sort'],v['value']])
                else:
                    facts.append([row['table'],args]);continue
                break
            else:
                ready.append((json.dumps(sorted(facts),separators=(',',':')),node,sorted(facts)))
        if not ready:raise ValueError('cyclic or missing constructor producer: unsupported DAG contract')
        ready.sort()
        keys=[key for key,_,_ in ready]
        assert len(set(keys))==len(keys),'duplicate equal constructors should already be repaired'
        for _,node,facts in ready:
            mapping[node]=len(nodes);nodes.append(facts);todo.remove(node)
    return nodes,mapping


def digest(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':'),sort_keys=True).encode()).hexdigest()


def extension(entry,completion):
    """Exact constructor embedding, necessary but not sufficient completion."""
    index={}
    for node,facts in enumerate(completion):
        for table,args in facts:
            key=json.dumps([table,args],separators=(',',':'))
            if key in index and index[key]!=node:raise ValueError('nonfunctional constructor catalog')
            index[key]=node
    mapping={}
    for node,facts in enumerate(entry):
        outputs=[]
        for table,args in facts:
            translated=[[k,s,mapping[v] if k=='eq' else v] for k,s,v in args]
            out=index.get(json.dumps([table,translated],separators=(',',':')))
            if out is None:return None
            outputs.append(out)
        if len(set(outputs))!=1:return None
        mapping[node]=outputs[0]
    return sorted(mapping.items())


def skeleton(nodes):
    """Conservative invariant grouping; collisions only keep MORE rows together.

    Get/SubTuple scalar arguments are ignored, but boundary Input identities
    and all directed argument positions/sharing are retained. No target used.
    """
    colors=['Expr']*len(nodes)
    for _ in range(8):
        outgoing=[[] for _ in nodes];incoming=[[] for _ in nodes]
        for dst,facts in enumerate(nodes):
            for table,args in facts:
                signature=[table,[[kind,sort,colors[value] if kind=='eq' else value if table=='Input' else '*']
                                   for kind,sort,value in args]]
                outgoing[dst].append(signature)
                for position,(kind,sort,value) in enumerate(args):
                    if kind=='eq':incoming[value].append([position,colors[dst],signature])
        colors=[digest([sorted(outgoing[i]),sorted(incoming[i])]) for i in range(len(nodes))]
    return digest(sorted(colors))


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    raw=json.loads(args.runtime.read_text());records=[];native=0
    for case in raw['cases']:
        assert case['fixed_point']['status']=='pass'
        before,bmap=canonical(case['initial']);after,amap=canonical(case['final'])
        if 'native_final' not in case:raise ValueError('missing native reference')
        ref,_=canonical(case['native_final'])
        assert ref==after, f"native final differs: {case['id']}"
        native+=1
        initial_anchors={(a['sort'],a['old']):a['now'] for a in case['initial']['anchors']}
        final_anchors={(a['sort'],a['old']):a['now'] for a in case['final']['anchors']}
        assert initial_anchors.keys()==final_anchors.keys()
        port_map={}
        for anchor,node in initial_anchors.items():
            old,new=bmap[node],amap[final_anchors[anchor]]
            assert old not in port_map or port_map[old]==new
            port_map[old]=new
        assert len(port_map)==len(before),'missing actual returned binding/anchor'
        # Native exports carry no source anchors. Reconstruct them using exact
        # functional constructor lookup in the independently executed graph.
        assert extension(before,ref)==sorted(port_map.items()), 'native port mapping differs'
        # Every established input fact must survive under the actual forwarding.
        for node,facts in enumerate(before):
            for table,arguments in facts:
                projected=[[kind,sort,port_map[value] if kind=='eq' else value] for kind,sort,value in arguments]
                assert [table,projected] in after[port_map[node]]
        records.append(dict(id=case['id'],entry=before,completion=after,
                            entry_key=digest(before),skeleton_key=skeleton(before),completion_key=digest(after),
                            actual_port_map=sorted(port_map.items()),roots=case['metadata']['roots'],
                            runs=len(case['steps']),source_sha256=case['source_sha256'],
                            program_sha256=case['program_sha256']))
    # Repeated syntax/aliases with identical initial graph never cross splits.
    unique={}
    for r in records:
        if r['entry_key'] in unique:assert unique[r['entry_key']]['completion_key']==r['completion_key']
        else:unique[r['entry_key']]=r
    groups=collections.defaultdict(list)
    for r in unique.values():groups[r['completion_key']].append(r)
    admitted=[];excluded=[]
    for key,rows in sorted(groups.items()):
        for row in rows:
            bucket=int(row['skeleton_key'][:8],16)%10
            row['split']='train' if bucket<6 else 'validation' if bucket<8 else 'test'
        # Known completions, genuinely held entrance skeletons; no parameter-
        # renamed skeleton can cross partitions, even across completion labels.
        if {r['split'] for r in rows}!={'train','validation','test'}:
            excluded.append(dict(completion=key,unique_entries=len(rows),splits=sorted({r['split'] for r in rows})));continue
        admitted.extend(rows)
    counts=collections.Counter(r['split'] for r in admitted)
    result=dict(schema='eggfuse-real-multi-entry-corpus/v1',records=admitted,
                summary=dict(runtime_cases=len(records),native_exact_final_pass=native,
                             unique_initial_graphs=len(unique),completion_shapes=len(groups),
                             multi_entry_shapes=sum(len(v)>1 for v in groups.values()),
                             admitted_completion_shapes=len({r['completion_key'] for r in admitted}),
                             split_counts=dict(counts),excluded_groups=excluded),
                contract='Known completion templates, unseen entry skeleton groups with Get/SubTuple scalar literals erased for splitting. Actual scalar literals retained for execution/features. No whole-program or novel-completion guarantee.',
                runtime_sha256=hashlib.sha256(args.runtime.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))


if __name__=='__main__':main()
