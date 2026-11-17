"""Same-graph layout sweep. Device execution precedes independent source audit."""
import argparse,hashlib,json,time,platform
from pathlib import Path
import numpy as np
import mlx.core as mx
from catalog import Catalog,leaf,ref
from device import Device,LIVE,FORWARD
from reference import SourceGraph,packet_term


def case(rows,length,count,seed):
    c=Catalog();f=c.add('F',('x',),[('f',10,('x',),1)])
    h=c.add('H',('y','c'),[('h',20,('y','c'),2)])
    plan=c.compose(f,h,{'y':'f'},'FH')
    rng=np.random.default_rng(seed);chosen=rng.permutation(rows*length)[:3*count].reshape(count,3)
    coords=[[(int(v)//length,int(v)%length) for v in group] for group in chosen]
    instances=[];proposals=[]
    for i,((fr,ft),(hr,ht),(dr,dt)) in enumerate(coords):
        nr,nt=coords[(i+1)%count][0]
        instances.extend([(fr,ft,f,[leaf(100+i)],fr),(hr,ht,h,[ref(fr,ft,1),ref(nr,nt,1)],hr)])
        proposals.append([plan,fr,ft,1,hr,ht,1,dr,dt,0,dr])
    return c,instances,np.array(proposals,np.int32)


def audit(c,d,instances,packet,stage):
    src=SourceGraph(c,instances);errors=[];checked=0
    for row,pos,tpl,_,_ in instances:
        for port in range(len(c.templates[tpl].ports)):
            q=ref(row,pos,port);checked+=1
            actual=packet_term(packet,q,d.length);expected=src.term(q,stage)
            if actual!=expected:errors.append(dict(address=q,actual=actual,expected=expected))
    return dict(checked=checked,errors=errors)


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not mx.metal.is_available():raise RuntimeError('Metal required; no CPU fallback')
    mx.set_default_device(mx.gpu);records=[]
    for rows,length,count in [(2,8,4),(4,8,8),(4,16,12)]:
        for seed in [19,71]:
            c,instances,proposals=case(rows,length,count,seed);d=Device(c,rows,length,2*count)
            initial=d.initialize(instances)
            def execute(state,p):
                state,one=d.publish(state,1,rounds=2)
                first=d.view(state,d.all_queries())
                state,transfer=d.transfer_batch(state,p)
                state,two=d.publish(state,2,rounds=2)
                last=d.view(state,d.all_queries())
                return state,one,transfer,two,first,last
            result=mx.compile(execute)(initial,mx.array(proposals));mx.eval(result)
            # Only after all GPU execution: decode observed packets and run oracle.
            state,one,transfer,two,first,last=result
            hp=lambda p:{k:np.array(v) for k,v in p.items()}
            first,last=hp(first),hp(last);before=audit(c,d,instances,first,1);after=audit(c,d,instances,last,2)
            record=dict(rows=rows,length=length,source_instances=2*count,seed=seed,one_graph=True,
                all_transfers_accepted=bool(mx.all(transfer['accepted'])),active_instances=int(mx.sum(state['kind']==LIVE)),
                forwarding_records=int(mx.sum(state['kind']==FORWARD)),active_payloads=int(mx.sum(state['arena_owner']>=0)),
                run1_pending=int(one['pending']),run2_pending=int(two['pending']),run1_audit=before,run2_audit=after,
                state_tensor_bytes_before=sum(v.size*v.itemsize for v in initial.values()),
                state_tensor_bytes_after=sum(v.size*v.itemsize for v in state.values()),
                shared_library_bytes=sum(v.size*v.itemsize for v in d.lib.values()),
                source_boundary_references=3*count,target_boundary_references=2*count,
                source_member_instruction_copies=0,target_member_instruction_copies=0,
                permanent_instance_pair_matrices=0,cpu_corrections=0,model_executed=False,union_executed=False)
            record['pass']=not before['errors'] and not after['errors'] and record['all_transfers_accepted'] and record['run1_pending']==record['run2_pending']==0 and record['active_payloads']==count
            records.append(record);print(json.dumps({k:record[k] for k in ('rows','length','seed','active_payloads','forwarding_records','pass')}),flush=True)
            np.savez_compressed(a.output/f'graph-{rows}-{length}-{seed}.npz',**{f'state_{k}':np.array(v) for k,v in state.items()},**{f'packet_{k}':v for k,v in last.items()})
    result=dict(status='pass' if all(x['pass'] for x in records) else 'difference',scope='deterministic compressed-template GPU view/ownership foundation, not neural egraph feasibility',
        records=records,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        environment=dict(platform=platform.platform(),device=str(mx.default_device())),
        limitations=['no union or cross-instance congruence engine','no neural template/binding proposal generation',
                     'full same-graph address bank is temporary and can be expensive','functional arena updates and source-ordered transfer loop',
                     'reported state bytes are tensor element footprints, not allocator peaks or RSS; fixed arenas and forwarding headers remain',
                     'pure finite constructor plans, at most 32 template ports; no mutable effects or eggcc integration'])
    (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
