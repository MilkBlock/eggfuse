"""Paired interventions for semantic reads and provenance, after the device run."""
import numpy as np
if __package__:
    from .check import discrete, relations
else:
    from check import discrete, relations


def request_decisions(d,g,first,second):
    a,b,r=d['a'][g],d['b'][g],d['requests'][g]
    full,_,_,_,_=relations(d['template'],a,d['a_port'][g],d['phase'][g],d['committed'][g],d['external'][g])
    source={(i,j):tuple(map(int,[*row,frame[1]])) for i,row in enumerate(a) for j,frame in enumerate(b) if row[0]==frame[0]}
    def one(frame):return {key:frame[key][g] for key in ('active','pointers','rows')}
    supplied={slot:record for slot,(i,j),record in discrete(one(first)) if source.get((i,j))==record}
    references={row[:2] for row in supplied.values()};candidates=discrete(one(second))
    chosen=[];legal=[];ready=[]
    for ri,(lo,lh,so,sh,tag) in enumerate(r):
        read,origin=(lo,lh),(so,sh);live=origin in full[read];legal.append(live)
        ready.append(not live or origin in references)
        binds=[(pi,row) for _,(pi,qi),row in candidates if qi==ri]
        if not live:chosen.append(not binds);continue
        if len(binds)!=1:chosen.append(False);continue
        pi,received=binds[0];parent=supplied.get(pi)
        chosen.append(parent is not None and parent[:2]==origin and received==(so,sh,tag,parent[3],parent[4]))
    return tuple(np.asarray(x,dtype=bool) for x in (legal,chosen,ready))


def paired_controls(data,first,second,semantic_choices):
    """Return pair-level graph/probe counts on complete 4-state × 2-origin groups."""
    choices=np.asarray(semantic_choices)
    if choices.shape!=data['requests'].shape[:2] or choices.dtype.kind not in 'biu' or not np.isin(choices,(0,1)).all():
        raise ValueError('pass hard equality decisions [graphs, 4]')
    selections={}
    for g,key in enumerate(zip(data['group_id'],data['state'],data['variant'])):
        if key in selections:raise ValueError('duplicate intervention graph')
        selections[key]=g
    truth,emitted,ready=(np.stack(seq) for seq in zip(*(request_decisions(data,g,first,second) for g in range(len(choices)))))
    result={}
    def pair(name,where,i,j):
        flags=np.asarray(where,bool);correct=(choices[i]==truth[i])&(choices[j]==truth[j]);emit=emitted[i]&emitted[j];avail=ready[i]&ready[j]
        for subset in ('all','blind') if data['blind'][i] else ('all',):
            stats=result.setdefault(subset,{}).setdefault(name,dict(probes=0,both_semantic_correct=0,both_emissions_exact=0,
                                                                    required_parents_ready=0,both_emissions_exact_given_parents=0))
            for k,v in dict(probes=flags,both_semantic_correct=flags&correct,both_emissions_exact=flags&emit,
                            required_parents_ready=flags&avail,both_emissions_exact_given_parents=flags&avail&emit).items():stats[k]+=int(v.sum())
    for group in sorted(set(data['group_id'])):
        for name,x,y in [('pre_to_post',0,1),('nonmerge_to_post',2,1),('post_to_external',1,3)]:
            for variant in (0,1):
                left,right=selections[group,x,variant],selections[group,y,variant]
                np.testing.assert_array_equal(data['requests'][left],data['requests'][right])
                pair(name,truth[left]!=truth[right],left,right)
        for state in (1,3):
            left,right=selections[group,state,0],selections[group,state,1]
            changed=(data['requests'][left,:,2:4]!=data['requests'][right,:,2:4]).any(-1)
            if not (changed.sum()==1 and (data['requests'][left,:,:2]==data['requests'][right,:,:2]).all()):
                raise ValueError('origin switch must preserve the read endpoint')
            pair('same_class_origin_switch_'+('post' if state==1 else 'external'),changed&truth[left]&truth[right],left,right)
    return result
