"""Recover actual nested merge-constructor results, guarded by source RHS/effect/arguments and corresponding write."""
import argparse,json
from collections import Counter
from pathlib import Path


def additions(folder,program):
    data=json.loads((folder/'references.json').read_bytes())
    candidates=json.loads((folder/'candidates.json').read_bytes())
    events=json.loads((folder/'audit.json').read_bytes())['events']
    src=json.loads(program.read_bytes())['recipe'];tables=src['tables'];ids={t['name']:i for i,t in enumerate(tables)}
    merges={}
    for t,v in enumerate(tables):
        merge=v.get('merge_expr') or {}
        output=merge.get('call',{}).get('table')
        if output in ids and merge.get('args')==[{'var':'old'},{'var':'new'}]:merges[t]=ids[output]
    by_run={}
    for ordinal,(run,offset,_,_,_) in enumerate(data['lhs'],1):by_run[run,offset]=ordinal
    extras={};stat=Counter();examples=[]
    for run,evs in enumerate(events,1):
        for i,birth in enumerate(evs):
            if birth[0]!='birth' or birth[1] not in merges.values():continue
            _,t,args,value,physical,source=birth;stat['births_of_merge_constructor']+=1
            if source is None:
                stat['repair_without_source_rhs']+=1;continue
            ordinal=by_run[run,source[0]];binding=data['lhs'][ordinal-1];assert binding[2]==source[1]
            # The *same RHS* must install that exact new constructor result in the merged function.
            writes=[ev for ev in evs[i+1:] if ev[0]=='write' and ev[2]==source and merges.get(ev[3])==t and ev[6]==args[0] and ev[7]==value]
            sites=[]
            for write in writes:
                _,_,_,table,index,_,old,new=write
                for op,ft,(_,row),candidate in candidates[ordinal-1]:
                    if ft==table and row==index and candidate==args[1]:sites.append((op,table,index))
            if len(sites)!=1:
                stat['missing_or_ambiguous_merge_site']+=1;continue
            op,table,index=sites[0];stat['source_merge_effect_exact']+=1
            # A negative encoded site identifies the nested merge constructor of this specific set operation.
            extras.setdefault(ordinal,[]).append([-op-1,t,[0,physical],run,[*args,value]])
            if len(examples)<4:
                examples.append(dict(run=run,rhs=ordinal,rule=source[1],source_set_effect=op,merge_table=tables[table]['name'],
                                     merge_constructor=tables[t]['name'],physical_fact=physical,function_row=index,old=args[0],candidate=args[1],result=value))
    return extras,dict(stat),examples


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('data','ref','corpus','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    from versions import measure
    out={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        program=a.ref/n/'program.json' if n in ('sum-bits','dot-product') else a.corpus/n/'program.json'
        folder=a.data/f'v4-{n}';extra,counts,examples=additions(folder,program)
        sample=measure(folder,extra)
        out[n]=dict(census=sample,merge_ports=counts,examples=examples)
        print(n,counts,sample['tiers']['same_physical_union'],sample['tiers']['cross_address_union'],flush=True)
        a.out.write_text(json.dumps(out,indent=1)+'\n')
