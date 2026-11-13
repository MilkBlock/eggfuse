"""Device-resident Cell-to-Cell state generation over Bake-certified entries.

This is an isolated, bounded dataflow experiment, not a full source executor.
Only initial facts bootstrap seeds. No recorded rule applications are loaded.
Floating states encode terms; exact symbolic interfaces stay in shared plans.
They are NOT equality proofs, and this version has no learned ridge transition.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import mlx.core as mx
from cell_token_successors import compile_catalog,match_consumer

WIDTH=32


def vector(key):
    seed=int.from_bytes(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).digest()[:8],'little')
    return np.random.default_rng(seed).normal(0,1/np.sqrt(WIDTH),WIDTH).astype(np.float32)


def matrix(table,position):
    seed=int.from_bytes(hashlib.sha256(f'{table}:{position}'.encode()).digest()[:8],'little')
    return np.random.default_rng(seed).normal(0,1/np.sqrt(WIDTH),(WIDTH,WIDTH)).astype(np.float32)


def bootstrap(program,catalog,limit=256):
    """One initial constructor query phase, never called during device rollout."""
    tables={t['name']:t for t in program['recipe']['tables']};facts=[];all_facts=[]
    def value(v):
        if 'eq' in v:return ('initial',v['sort'],v['eq'])
        return ('scalar',v['sort'],json.dumps(v.get('value'),sort_keys=True))
    for row in program['initial']:
        if row.get('subsumed'):continue
        args=[]
        for v,sort in zip(row['values'],tables[row['table']]['schema']):
            if 'eq' in v:args.append(value(v))
            else:args.append(('literal',json.dumps(dict(literal=v.get('value'),sort=sort),sort_keys=True)))
        fact=(row['table'],tuple(args),True);all_facts.append(fact)
        if tables[row['table']]['kind']=='constructor':facts.append(fact)
    seeds=[];marks=[]
    for rid,rule in enumerate(program['recipe']['rules']):
        if catalog['cells'][rid] is None:
            entries,full=([dict(inputs=(),witnesses=())],False) if not rule['query'] else match_consumer(rule,all_facts,limit)
            if entries or full:marks.append(dict(rule=rid,reason='initial matches blocked by unsupported effects',bindings=len(entries),capacity_exhausted=full))
            continue
        if any(tables.get(a['call'].get('table'),{}).get('kind')!='constructor' for a in rule['query']):continue
        entries,full=([dict(inputs=(),witnesses=())],False) if not rule['query'] else match_consumer(rule,facts,limit)
        if full:marks.append(dict(rule=rid,reason='bootstrap capacity'));continue
        if entries:seeds.append(dict(rule=rid,entries=entries))
    return seeds,marks


def layout(program,catalog,seeds,depth=2,max_tokens=4096,speculate_stages=False):
    rules=program['recipe']['rules'];groups=[];levels=[];count=0;marks=[]
    for seed in seeds:
        size=len(seed['entries'])
        if count+size>max_tokens:marks.append(dict(rule=seed['rule'],reason='seed capacity',tokens=size));continue
        count+=size;groups.append(dict(rule=seed['rule'],size=size,seed=seed))
    levels.append(list(range(len(groups))));by_rule=defaultdict(list)
    for edge in catalog['edges']:by_rule[edge['producer']].append(edge)
    for level in range(depth):
        next_level=[]
        for parent in levels[-1]:
            src=groups[parent]
            for edge in by_rule[src['rule']]:
                cid=edge['consumer'];size=src['size']
                reason=None
                if edge['source_set']!=edge['target_set']:
                    if not speculate_stages:reason='source stage boundary'
                    else:marks.append(dict(parent=parent,rule=cid,reason='speculative stage requires CPU validation',tokens=size))
                if catalog['cells'][cid] is None:reason='unsupported consumer effect'
                elif count+size>max_tokens:reason='token capacity'
                if reason:marks.append(dict(parent=parent,rule=cid,reason=reason,tokens=size));continue
                count+=size;next_level.append(len(groups));groups.append(dict(rule=cid,size=size,parent=parent,edge=edge))
        levels.append(next_level)
    # A depth bound never masquerades as saturation. No duplicate-proof claim.
    for index in levels[-1]:
        if by_rule[groups[index]['rule']]:marks.append(dict(parent=index,reason='depth boundary',tokens=groups[index]['size']))
    return dict(groups=groups,levels=levels,marks=marks,tokens=count)


def execute(program,plan,initial,xp,weight_cache=None):
    """Static host graph construction only; no eval, scalar reads or callbacks.

    A group is a batch of Cell instances. RHS internal expressions are columns
    of that group, not individually allocated runtime node/token objects.
    """
    cache={} if weight_cache is None else weight_cache
    def const(key,make):
        if key not in cache:cache[key]=xp.array(make())
        return cache[key]
    states=[];sources=[]
    for index,group in enumerate(plan['groups']):
        rid=group['rule'];rule=program['recipe']['rules'][rid];batch=group['size']
        if 'seed' in group:
            frame=initial[index];env={slot:frame[:,slot,:] for slot,s in enumerate(rule['slots']) if s['definition']=='query'}
        else:
            parent=sources[group['parent']]
            env={int(slot):read_ref(ref,parent,batch,xp,const) for slot,ref in group['edge']['inputs']}
        refs={('input',slot):value for slot,value in env.items()}
        def operand(arg):
            if 'slot' in arg:return env[arg['slot']]
            return read_ref(('literal',json.dumps(arg,sort_keys=True)),refs,batch,xp,const)
        for op_index,op in enumerate(rule['effects']):
            kind=op['kind']
            if kind=='copy':env[op['dst']]=operand(op['arg'])
            elif kind=='construct':
                name=op['call']['table'];value=xp.broadcast_to(const(('bias',name),lambda:vector(('constructor',name))),(batch,WIDTH))
                for position,arg in enumerate(op['args']):
                    value=value+operand(arg)@const(('matrix',name,position),lambda:matrix(name,position))
                value=xp.tanh(value);env[op['dst']]=value;refs[('result',op_index)]=value
            elif kind not in ('set','union'):raise ValueError('unadmitted effect')
            # Set/union structure is part of the proved shared template, not
            # inferred from proximity of these floating vectors.
        columns=[env.get(slot,xp.zeros((batch,WIDTH),dtype=xp.float32)) for slot in range(len(rule['slots']))]
        states.append(xp.stack(columns,axis=1) if columns else xp.zeros((batch,0,WIDTH),dtype=xp.float32))
        sources.append(refs)
    return states


def read_ref(ref,sources,batch,xp,const):
    ref=tuple(ref)
    if ref[0]=='literal':return xp.broadcast_to(const(ref,lambda:vector(ref)),(batch,WIDTH))
    return sources[ref]


def initial_states(program,plan):
    states={}
    for i,g in enumerate(plan['groups']):
        if 'seed' not in g:continue
        frame=np.zeros((g['size'],len(program['recipe']['rules'][g['rule']]['slots']),WIDTH),np.float32)
        for row,e in enumerate(g['seed']['entries']):
            for slot,identity in e['inputs']:frame[row,slot]=vector(identity)
        states[i]=frame
    return states


def main():
    p=argparse.ArgumentParser();p.add_argument('program',type=Path);p.add_argument('output',type=Path);p.add_argument('--depth',type=int,default=2);p.add_argument('--speculate-stages',action='store_true');args=p.parse_args()
    program=json.loads(args.program.read_text());start=time.perf_counter();catalog=compile_catalog(program['recipe']);seeds,marks=bootstrap(program,catalog);plan=layout(program,catalog,seeds,args.depth,speculate_stages=args.speculate_stages);seed_values=initial_states(program,plan);prepare_seconds=time.perf_counter()-start
    if not seed_values:raise ValueError('no initial closed Cell entries')
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    initial={k:mx.array(v) for k,v in seed_values.items()};mx.eval(initial)
    start=time.perf_counter();kernel=mx.compile(lambda inputs:execute(program,plan,inputs,mx));states=kernel(initial);mx.eval(states);gpu_seconds=time.perf_counter()-start
    # CPU reference is evaluated only after the complete device chain finishes.
    start=time.perf_counter();expected=execute(program,plan,seed_values,np);cpu_seconds=time.perf_counter()-start
    errors=[]
    for a,b in zip(states,expected):np.testing.assert_allclose(np.array(a),b,rtol=2e-4,atol=2e-5);errors.append(float(np.max(np.abs(np.array(a)-b))))
    result=dict(scope='bounded isolated constructor Cell state generation; not source-program execution',program_sha256=program['sha256'],seed_tokens=sum(g['size'] for g in plan['groups'] if 'seed' in g),generated_tokens=sum(g['size'] for g in plan['groups'] if 'parent' in g),identity_entries_removed=catalog['identity_entries_removed'],generation_counts=[sum(plan['groups'][i]['size'] for i in level) for level in plan['levels']],cell_templates=len({g['rule'] for g in plan['groups']}),cell_batches=len(plan['groups']),cpu_bootstrap_calls=1,cpu_matching_during_rollout=0,intermediate_device_readbacks=0,cpu_encode_generated_tokens=0,final_state_values=sum(int(a.size) for a in states),max_cpu_gpu_error=max(errors),prepare_seconds=prepare_seconds,gpu_first_call_seconds=gpu_seconds,cpu_reference_seconds=cpu_seconds,marks=marks+plan['marks'],saturation_claimed=False,speculative_stages=args.speculate_stages,backpropagation=False,learned_transition=False,limitations=['Initial query bootstrap is CPU work; input encoding is fixed, not learned','No full source schedule execution; cross-ruleset transitions are marked, and speculative ones need validation','No novelty/duplicate elimination; token counts are derivations, not new facts','Exact structure is in shared templates and symbolic boundary provenance; float codes are not equality proofs','Generated states are term encodings, not a trained semantic completion model','Capacity/depth boundaries require continuation or CPU handling; no runtime speedup claimed'])
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='marks'},indent=2))

if __name__=='__main__':main()
