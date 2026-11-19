"""Independent source-witness audit, performed after both model Runs."""
from collections import Counter
import numpy as np
if __package__:
    from .runtime import partition_record
else:
    from runtime import partition_record


def components(nodes, edges):
    neighbors={p:{p} for p in nodes}
    for left,right in edges:
        neighbors[left].add(right);neighbors[right].add(left)
    found={}
    for root in nodes:
        seen={root};todo=[root]
        while todo:
            for child in neighbors[todo.pop()]-seen:
                todo.append(child);seen.add(child)
        found[root]=seen
    return found


def relations(t,a,ap,phase,committed,ext):
    replay,secondary,event=partition_record(t,a,ap,phase,committed,ext)
    by_port={(int(row[0]),int(p)):tuple(map(int,row[:2])) for row,p in zip(a,ap)}
    nodes=set(by_port.values());edges=[];potential=[]
    for proof in t['certificates']:
        for owner in (0,1):
            link=by_port[owner,proof['left_port']],by_port[owner,proof['right_port']]
            potential.append(link)
            if phase[owner]>=proof['visible_from_stage'] and committed[owner]:edges.append(link)
    if ext[0]:edges.append((tuple(map(int,ext[1:3])),tuple(map(int,ext[3:5]))))
    direct=components(nodes,edges);full=components(nodes,[*edges,*secondary])
    if full!=replay:raise ValueError('reconstructed partition disagrees with real CPU replay')
    return full,direct,components(nodes,potential),bool(secondary),event


def discrete(stage):
    active,pointers,rows=(np.asarray(stage[k]) for k in ('active','pointers','rows'))
    if (active.ndim!=1 or pointers.shape!=(len(active),2) or rows.shape!=(len(active),5)
        or any(v.dtype.kind not in 'biu' for v in (active,pointers,rows)) or not np.isin(active,[0,1]).all()):
        raise ValueError('expected categorical active/pointers and five integer output fields per slot')
    return [(int(s),tuple(map(int,pointers[s])),tuple(map(int,rows[s]))) for s in np.flatnonzero(active)]


def summary(expected,counts,semantic,active):
    missing=len(set(expected)-counts.keys());dups=sum(n-1 for n in counts.values());illegal=active-sum(counts.values())
    sem_missing=len(set(expected)-semantic.keys());binding_complete=not(missing or dups or illegal)
    return dict(obligations=len(expected),nonempty=bool(expected),binding_complete=binding_complete,
                complete=binding_complete and not sem_missing,missing=missing,semantic_missing=sem_missing,
                duplicates=dups,illegal=illegal,active_outputs=active,valid_unique=len(counts))


def audit_graph(d,g,first,second):
    a,b,req,ap,phase,commit,ext=[d[k][g] for k in ('a','b','requests','a_port','phase','committed','external')]
    full,direct,potential,secondary,event=relations(d['template'],a,ap,phase,commit,ext)
    by_origin={tuple(map(int,x[:2])):(i,j) for i,x in enumerate(a) for j,y in enumerate(b) if x[0]==y[0]}
    made={(i,j):(*map(int,a[i]),int(b[j,1])) for i,j in by_origin.values()}
    expected={};class_active=[];only_secondary=set();pending=set()
    for ri,r in enumerate(req):
        read=tuple(map(int,r[:2]));origin=tuple(map(int,r[2:4]));legal=origin in full[read];class_active.append(legal)
        if legal:
            ident=by_origin[origin];row=made[ident]
            expected[(*ident,ri)]=(row[0],row[1],int(r[4]),row[3],row[4])
            if origin not in direct[read]:only_secondary.add(ri)
        elif origin in potential[read]:pending.add(ri)
    def at(stage):return {k:stage[k][g] for k in ('active','pointers','rows')}
    f=at(first);s=at(second);em1=discrete(f);em2=discrete(s)
    bound=Counter();exact=Counter();parent={}
    for slot,ident,row in em1:
        if ident not in made:continue
        bound[ident]+=1;ok=row==made[ident];parent[slot]=(ident,ok)
        if ok:exact[ident]+=1
    run1=summary(made,bound,exact,len(em1));available={k for k in expected if k[:2] in exact}
    bound=Counter();exact=Counter();extra=Counter({k:0 for k in (
        'invalid_request','absent_parent','illegal_producer','wrong_parent','wrong_parent_same_eclass',
        'wrong_parent_when_available','illegal_equality','early_local_equality','uncommitted_local_equality',
        'unrelated_local_equality','cross_instance_contamination','bad_parent_row','bad_result_row',
        'secondary_correct','pending_claims','specified_origin_exact')})
    for _,(pi,ri),row in em2:
        if not 0<=ri<len(req):extra['invalid_request']+=1;continue
        read=tuple(map(int,req[ri,:2]));wanted=tuple(map(int,req[ri,2:4]));wanted_key=(*by_origin[wanted],ri)
        if not class_active[ri]:
            extra['illegal_equality']+=1
            if read[0]!=wanted[0]:extra['cross_instance_contamination']+=1
            elif ri in pending:
                reason='early_local_equality' if phase[read[0]]==0 else 'uncommitted_local_equality'
                extra[reason]+=1;extra['pending_claims']+=1
            else:extra['unrelated_local_equality']+=1
        if not 0<=pi<len(f['active']) or not f['active'][pi]:extra['absent_parent']+=1;continue
        if pi not in parent:extra['illegal_producer']+=1;continue
        ident,parent_ok=parent[pi];source=made[ident][:2]
        if source!=wanted:
            extra['wrong_parent']+=1;extra['wrong_parent_same_eclass']+=int(source in full[wanted]);extra['wrong_parent_when_available']+=int(wanted_key in available);continue
        if not class_active[ri]:continue
        key=(*ident,ri);bound[key]+=1;row_ok=row==expected[key]
        extra['bad_parent_row']+=int(not parent_ok);extra['bad_result_row']+=int(not row_ok)
        if parent_ok and row_ok:exact[key]+=1
    extra['specified_origin_exact']=sum(1 for k in expected if bound[k]==exact[k]==1)
    extra['secondary_correct']=sum(1 for k in expected if k[-1] in only_secondary and bound[k]==exact[k]==1)
    run2=summary(expected,bound,exact,len(em2));run2.update(extra)
    run2.update(parent_ready=len(available)==len(expected),unavailable_parent_obligations=len(expected)-len(available),
                secondary_obligations=len(only_secondary),secondary_event=secondary,pending_conditional_requests=len(pending),
                outstanding_legal_obligations=run2['semantic_missing'],logical_legal_requests=sum(class_active))
    return run1,run2,class_active,event


def aggregate(rows):
    totals={k:int(sum(int(g[k]) for g in rows)) for k in rows[0]}
    totals['graphs']=len(rows);totals['nonempty_graphs']=totals.pop('nonempty');totals['complete_graphs']=totals.pop('complete')
    totals['binding_complete_graphs']=totals.pop('binding_complete');totals['nonempty_complete_graphs']=sum(bool(g['nonempty'] and g['complete']) for g in rows)
    if 'parent_ready' in totals:
        totals['parent_ready_nonempty_graphs']=sum(bool(g['nonempty'] and g['parent_ready']) for g in rows)
        totals['parent_ready_nonempty_complete_graphs']=sum(bool(g['complete'] and g['nonempty'] and g['parent_ready']) for g in rows)
    totals['per_graph']=rows
    return totals


def audit(data, first, second):
    reports=[[],[]];truth=[];events=[]
    for g in range(len(data['a'])):
        r1,r2,active,event=audit_graph(data,g,first,second);reports[0].append(r1);reports[1].append(r2);truth.append(active);events.append(event)
    return dict(run1=aggregate(reports[0]),run2=aggregate(reports[1]),
                both_complete_graphs=sum(a['complete'] and b['complete'] for a,b in zip(*reports)),
                request_legal=truth, replay_cases=events)
