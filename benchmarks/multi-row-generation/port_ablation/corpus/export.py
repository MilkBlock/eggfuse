"""Export typed, ordered two-leaf boundary contracts from validated Pass 3 catalogs."""
import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sort_name(sort):
    return sort['name']


def stage(left_sorts, right_sorts, checks, outputs):
    return dict(left_width=len(left_sorts), right_width=len(right_sorts), checks=checks, outputs=outputs,
                left_sorts=left_sorts, right_sorts=right_sorts,
                output_sorts=[(left_sorts,right_sorts)[side][i] for side,i in outputs])


def table_sorts(tables, name):
    return [sort_name(s) for s in tables[name]['schema']]


def make_stage(producer, effect, tables):
    operands = list(effect['args'])
    if effect['op'] == 'set':
        operands.append(effect['value'])
    else:
        require(effect['kind'] == 'construct', 'only published constructor/set facts can anchor a following Run')
    right = table_sorts(tables, effect['call']['table'])
    require(len(operands) == len(right) - int(effect['kind'] == 'construct'), 'inconsistent publication width')
    slots = {}
    left = []
    checks = []
    for column, arg in enumerate(operands):
        if 'slot' in arg:
            slot = arg['slot']
            if slot not in slots:
                slots[slot] = len(slots)
                left.append(sort_name(producer['slots'][slot]['sort']))
            src = [0, slots[slot]]
            require(left[src[1]] == right[column], 'effect source type mismatch')
        else:
            value = arg['literal']
            require(type(value) is int and abs(value) <= 16 and sort_name(arg['sort']) == right[column], 'unsupported literal')
            src = [2, value]
        checks.append([src, [1, column]])
    require(bool(left), 'no producer binding')
    return stage(left, right, checks, [[1,c] for c in range(len(right))])


def finish_stage(consumer, entry, tables, table_list):
    pivot = consumer['query'][entry['pivot']]
    anchor = table_sorts(tables, pivot['call']['table'])
    block = entry['block']; port = block['port']
    require(not block.get('steps'), 'multi-step residual not supported')
    checks=[]; occupied={}; rhs=[]; right=[]
    for c,arg in enumerate(pivot['args']):
        if 'literal' in arg:
            require(type(arg['literal']) is int, 'unsupported pivot literal')
            checks.append([[0,c],[2,arg['literal']]])
        elif arg['slot'] in occupied:
            checks.append([[0,c],[0,occupied[arg['slot']]]])
        else:
            occupied[arg['slot']] = c
    residual = []
    if port is not None:
        name = table_list[port['table']]['name']
        require(consumer['query'][port['atom']]['call']['table'] == name, 'residual table mismatch')
        residual = table_sorts(tables, name)
        require(len(residual) == len(port['key'])+1, 'residual key arity')
    for index, arg in enumerate(block['inputs']):
        if arg == 'PortResult':
            require(bool(residual), 'unbound PortResult')
            right.append(residual[-1]);rhs.append([1,len(block['inputs'])+len(residual)-1])
        else:
            c=arg['Anchor'];right.append(anchor[c]);rhs.append([0,c])
        checks.append([rhs[-1],[1,index]])
    if port is not None:
        base=len(right);right.extend(residual)
        def ref(arg):
            if 'Anchor' in arg: return [0,arg['Anchor']]
            value=arg['Literal'];require(len(value)==1 and type(next(iter(value.values()))) is int, 'unsupported residual literal')
            return [2,next(iter(value.values()))]
        for col,arg in enumerate(port['key']):checks.append([ref(arg),[1,base+col]])
        if port['check_result'] is not None:checks.append([ref(port['check_result']),[1,base+len(residual)-1]])
    return stage(anchor, right, checks, rhs)


class Graph:
    def __init__(self):
        self.nodes=[];self.edges=[];self.readouts=[]

    def node(self, kind, sort='none', ordinal=0):
        index=len(self.nodes);self.nodes.append(dict(kind=kind,sort=sort,ordinal=ordinal));return index

    def connect(self, u, kind, v):
        self.edges.append([u,kind,v])

    def build(self, stages, sorts):
        prior=[]
        for s, spec in enumerate(stages):
            sources=[]; operands={}; outputs=[]
            for side,columns in enumerate((spec['left_sorts'],spec['right_sorts'])):
                reader=self.node('read',ordinal=side)
                sources.append(reader)
                for col,name in enumerate(columns):
                    node=self.node('input_column',sorts[name],col)
                    self.connect(reader,'reads',node);operands[side,col]=node
                    if s==1 and side==0:self.connect(prior[col],'published_to',node)
            self.readouts.append(sources)
            for a,b in spec['checks']:
                test=self.node('equality')
                for side,col in (a,b):
                    if side==2:
                        # Raw literals are small constants of the contract, independent of template IDs.
                        operand=self.node('literal','integer',col)
                    else:operand=operands[side,col]
                    self.connect(operand,'tested_by',test)
            for col,(side,idx) in enumerate(spec['outputs']):
                value=self.node('output_column',sorts[spec['output_sorts'][col]],col)
                outputs.append(value);self.connect(operands[side,idx],'projected_to',value)
            prior=outputs
        return dict(nodes=self.nodes,edges=self.edges,readouts=self.readouts)


def family(graph, consider_sorts=False):
    # Isomorphism-invariant refinement. Column ordinals, literal values, sort names,
    # rule/table IDs and workload names are deliberately ignored for splitting. A
    # refinement collision can group additional shapes, never split isomorphs.
    features=[(n['kind'], n['sort'] if consider_sorts else '*') for n in graph['nodes']]
    for s,readouts in enumerate(graph['readouts']):
        for side,i in enumerate(readouts): features[i]+= (s,side)
    neighbors=[[] for _ in features]
    for u,typ,v in graph['edges']:
        neighbors[u].append(('out',typ,v));neighbors[v].append(('in',typ,u))
    colors=[digest(v) for v in features]
    for _ in range(12):
        colors=[digest((c,sorted((direc,typ,colors[j]) for direc,typ,j in ns))) for c,ns in zip(colors,neighbors)]
    return 'f-'+digest(sorted(colors))[:20]


def rule_key(rule):
    # Real atomic identity independent of recipe's local numeric rule ordinal.
    return 'r-'+digest([rule['metadata']['source_set'],rule['metadata']['name']])[:16]


def scan(label, path, records, composites):
    artifact=json.loads(path.read_text());recipe=artifact['recipe'];cat_path=ROOT/'workloads/pass3/catalogs'/f'{label}.json'
    catalog=json.loads(cat_path.read_text()); require(recipe['sha256']==catalog['recipe_sha256'],'recipe digest mismatch')
    for k in ('spine_blocks','iterative_bake'):require(catalog[k]==artifact[k],f'{k} differs from frozen catalog')
    tables={t['name']:t for t in recipe['tables']};sorts={s['name']:s['kind'] for t in tables.values() for s in t['schema']}
    entries=catalog['spine_blocks']['entries'];units=[[i] for i in range(len(entries))];ancestry=[set() for _ in entries]
    for join in catalog['iterative_bake']['joins']:
        li,ri,oi=join['left'],join['right'],join['output'];left,right=units[li],units[ri];unit=len(units)
        a,b=entries[left[-1]],entries[right[0]];producer,consumer=[recipe['rules'][e['consumer']] for e in (a,b)]
        effect=producer['effects'][oi];pivot=consumer['query'][b['pivot']]
        require(effect['call']['table']==pivot['call']['table'],'publication does not feed selected pivot')
        stages=[make_stage(producer,effect,tables),finish_stage(consumer,b,tables,recipe['tables'])]
        graph=Graph().build(stages,sorts);f=family(graph);parents=ancestry[li]|ancestry[ri];units.append(left+right);ancestry.append(parents|{f})
        info=dict(catalog=label,unit=unit,left=li,right=ri,output_operation=oi,source_rule=a['consumer'],consumer_rule=b['consumer'],
                  source_pivot=a['pivot'],consumer_pivot=b['pivot'],published_table=effect['call']['table'],lineage=sorted(ancestry[-1]),
                  source_ruleset=producer['metadata']['source_set'],consumer_ruleset=consumer['metadata']['source_set'],
                  source_rule_text=producer['metadata']['name'],consumer_rule_text=consumer['metadata']['name'])
        if len(left+right)!=2:
            composites.append(info);continue
        keys=[rule_key(r) for r in (producer,consumer)];key='t-'+digest([family(graph, consider_sorts=True),stages,keys])[:16]
        if key not in records:
            records[key]=dict(id=key,family_id=f,rule_ids=keys,stages=stages,graph=graph,provenance=[])
        records[key]['provenance'].append(info)
    return dict(catalog_sha256=hashlib.sha256(cat_path.read_bytes()).hexdigest(),recipe_sha256=recipe['sha256'],
                leaves=len(entries),learned_compositions=len(catalog['iterative_bake']['joins']))


def select_split(templates):
    groups=defaultdict(list)
    for t in templates:groups[t['family_id']].append(t)
    need=max(2,len(groups)//4)
    def score(families):
        remaining=[t for t in templates if t['family_id'] not in families]
        seen=[{t['rule_ids'][s] for t in remaining} for s in range(2)]
        warm=0; cold=0
        for f in families:
            for t in groups[f]:
                missing=sum(t['rule_ids'][s] not in seen[s] for s in range(2))
                warm += missing == 0
                cold += missing
        return (-warm, cold, digest(families))
    held=set(min(combinations(sorted(groups),need),key=score))
    training=[t for t in templates if t['family_id'] not in held]
    seen=[{t['rule_ids'][s] for t in training} for s in range(2)]
    for t in templates:
        t['split']='heldout' if t['family_id'] in held else 'train'
        t['atomic_seen_in_training']=[t['rule_ids'][s] in seen[s] for s in range(2)]
    return held


def main():
    parser=argparse.ArgumentParser();parser.add_argument('sum_bits_program',type=Path);parser.add_argument('raytrace_program',type=Path)
    args=parser.parse_args();records={};composites=[]
    files={label:scan(label,path,records,composites) for label,path in [('sum-bits',args.sum_bits_program),('raytrace',args.raytrace_program)]}
    templates=sorted(records.values(),key=lambda t:t['id']);held=select_split(templates)
    for c in composites:c['has_heldout_ancestor']=bool(held.intersection(c['lineage']))
    summary=dict(templates=len(templates),families=len({t['family_id'] for t in templates}),heldout_families=len(held),
                 by_split=dict(Counter(t['split'] for t in templates)),excluded_longer_units=len(composites),
                 longer_units_touching_holdout=sum(c['has_heldout_ancestor'] for c in composites),
                 max_source_columns=max(max(s['left_width'],s['right_width']) for t in templates for s in t['stages']))
    result=dict(schema='eggfuse.baked-two-leaf-port-contract/v1',catalogs=files,templates=templates,summary=summary,excluded_longer_units=composites)
    (HERE/'manifest.json').write_text(json.dumps(result,indent=1)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
