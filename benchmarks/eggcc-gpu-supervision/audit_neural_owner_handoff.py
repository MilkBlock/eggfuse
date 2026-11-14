"""GPU neural token + physical takeover on synthetic sealed Cell snapshots.

CPU exact execution initializes sealed source/target fixtures. GPU actually
computes both tokens and performs the transfer. This is integration validation,
not GPU generation of exact RHS values or a complete saturation runtime.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from neural_cell_samples import samples
from neural_cell_chains import chains
from neural_ordered_relations import OrderedCellTransition
from neural_owner_handoff import handoff
from device_slot_owners import pack,read,COLUMNS
from multi_entry_ridge import scalar


def fixture(recipe,record,width):
    plan=record['plan'];ref=record['reference']
    state=dict(keys=np.array([[plan['producer']],[plan['consumer']]],np.int32),
        slots=np.full((2,width),-1,np.int32),slot_roots=np.full((2,width),-1,np.int32),slot_valid=np.zeros((2,width),bool),
        generation=np.ones(2,np.int32),present=np.ones(2,bool),visible=np.ones(2,bool),settled=np.ones(2,bool),
        tokens=np.zeros((2,128),np.float32),scalar_codes=np.zeros((2,width,64),np.float32),scalar_valid=np.zeros((2,width),bool))
    for row,(rid,values) in enumerate(((plan['producer'],record['source_values']),(plan['consumer'],record['target_values']))):
        for slot,value in enumerate(values):
            state['slots'][row,slot]=value;state['slot_roots'][row,slot]=ref.root(value);state['slot_valid'][row,slot]=True
            if recipe['rules'][rid]['slots'][slot]['sort']['kind']!='eq':
                state['scalar_codes'][row,slot]=scalar(ref.scalar_values[value]);state['scalar_valid'][row,slot]=True
    return pack(state)


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=json.loads(a.trace.read_text());source=raw.get('recipe',raw);recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    started=time.perf_counter();records=[];base=samples(recipe,4,93003,records,ordered=True);transfers=[]
    chain,coverage=chains(recipe,records,ordered=True,transfers=transfers)
    width=max(len(r['slots']) for r in recipe['rules'])
    model=OrderedCellTransition(base['x'].shape[-1],base['relations'].shape[-1]);model.load_weights(str(a.weights))
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    parent=device({k:v[chain['parent']] for k,v in base.items()});dc=device(chain)
    first,source_tokens=model(parent['x'],parent['edges'],parent['mask'],parent['request'],parent['relations'])
    incoming=mx.where(dc['replace'][...,None],source_tokens[:,None,:],dc['tokens'])
    logits,tokens=model.transition(incoming,dc['edges'],dc['mask'],dc['request'],dc['relations'])
    mx.eval(first,source_tokens,logits,tokens)
    # Each independent fixture is a sealed, audited pair, not one growing graph.
    counts=dict(attempted=0,transferred=0,copied_fields=0,interface_failures=0,token_failures=0,
                blocked=0,value_mismatch=0,stale=0,occupied_destination=0)
    cases=[]
    for record in transfers:
        i=record['chain'];host=fixture(recipe,record,width);state=device(host)
        # The source token is the actual first network output, not the label code.
        state['tokens']=state['tokens'].at[0].add(source_tokens[i])
        plan={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in record['plan'].items()}
        out,marks=handoff(state,plan,mx.array(0),mx.array(1),mx.array(1),mx.array(1),logits[i],tokens[i],first[i]>=0,mx.array(True),mx)
        mx.eval(out,marks)
        moved=bool(marks['transferred']);counts['attempted']+=1;counts['transferred']+=moved;counts['blocked']+=not moved
        counts['copied_fields']+=int(marks['copied_fields'])
        for reason in ('value_mismatch','stale','occupied_destination'):counts[reason]+=int(not moved and bool(marks[reason]))
        logical=np.arange(2)[:,None];slots=np.arange(width)[None,:]
        after={k:np.array(v) for k,v in out.items()}
        for column in COLUMNS:
            if 'owner_'+column not in host:continue
            before=read(host,column,logical,slots,np);observed=read(after,column,logical,slots,np)
            counts['interface_failures']+=int(not np.array_equal(before,observed))
        counts['token_failures']+=int(moved and not np.array_equal(np.array(out['tokens'][1]),np.array(tokens[i])))
        counts['token_failures']+=int(not np.array_equal(np.array(out['tokens'][0]),np.array(state['tokens'][0])))
        if moved:
            # Poison released storage; logical source views must still resolve.
            after['owner_slots'][0,:]=123456
            counts['interface_failures']+=int(not np.array_equal(read(host,'slots',logical,slots,np),read(after,'slots',logical,slots,np)))
        cases.append(dict(producer=int(chain['producer'][i]),consumer=int(chain['consumer'][i]),transferred=moved))
    report=dict(scope='standalone neural-to-owner integration on CPU-initialized sealed snapshots; not GPU RHS execution',counts=counts,compiled_coverage=coverage,cases=cases,wall_seconds=time.perf_counter()-started,
                weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),token_outputs_from_gpu=True,exact_rhs_values_from_cpu_fixture=True,semantic_saturation_proved=False,speedup_claim=False)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(counts))
    if counts['interface_failures'] or counts['token_failures']:raise SystemExit(1)


if __name__=='__main__':main()
