"""Evaluate complete source obligations against actual emitted row identities."""
import numpy as np
if __package__:
    from .score import audit_graph, totals
else:
    from score import audit_graph, totals


def table_join(stage, left, right):
    """Evaluate all pairs as a Cartesian-product mask, independently of label construction."""
    dimensions=(len(left),len(right))
    def grid(point):
        side,col=point
        if side==2:return np.broadcast_to(np.int64(col),dimensions)
        if side not in (0,1):raise ValueError('unknown source table operand')
        return np.broadcast_to(left[:,None,col] if side==0 else right[None,:,col],dimensions)
    mask=np.ones(dimensions,dtype=bool)
    for lhs,rhs in stage['checks']:
        mask &= grid(lhs)==grid(rhs)
    rows=np.stack([grid(operand) for operand in stage['outputs']],axis=-1)
    li,ri=np.nonzero(mask)
    return list(zip(map(int,li),map(int,ri))),rows[li,ri]


def source_witnesses(stages, a, b, requests):
    ids,rows=table_join(stages[0],a,b)
    selected,results=table_join(stages[1],rows,requests)
    first={key:tuple(map(int,row)) for key,row in zip(ids,rows)}
    second={(*ids[parent],ri):tuple(map(int,row)) for (parent,ri),row in zip(selected,results)}
    return first,second


def consistent_candidate_reads(stage, requests):
    start = len(stage['outputs'])
    if stage['right_width'] == start:
        return True
    values = {}
    for row in requests:
        key = tuple(row[start:-1]); value = int(row[-1])
        if key in values and values[key] != value:
            return False
        values[key] = value
    return True


def audit(data,first,second):
    stages=data['stages'];reports=[[],[]]
    for i,(a,b,req) in enumerate(zip(data['a'],data['b'],data['requests'])):
        made,result=source_witnesses(stages,a,b,req)
        def frame(raw):return {k:np.asarray(raw[k][i]) for k in ('active','pointers','rows')}
        probe_data=data.get('probe')
        probe=None if probe_data is None else np.asarray(probe_data[i])
        payload=None
        if probe is not None and probe[0]>=0:
            p,q=tuple(probe[:2]),tuple(probe[2:4]);common=[c for c,(x,y) in enumerate(zip(made[p],made[q])) if x==y]
            if not common:raise ValueError('expected a real shared payload column')
            payload={key:tuple(row[c] for c in common) for key,row in made.items()}
        r1,r2=audit_graph(made,result,frame(first),frame(second),len(req),payload)
        # A controlled wrong twin must be the other candidate *for the varied
        # request position*. Both are known from actual source checks, and
        # alternative parents that also satisfy the request remain legal.
        r2['probe_wrong_twin']=0
        r2['probe_claims_exact']=0
        if probe is not None and probe[0]>=0:
            f,s=frame(first),frame(second);parent=tuple(probe[:2]);sibling=tuple(probe[2:4]);req_slot=int(probe[4])
            actual=[]
            for out_slot in np.flatnonzero(s['active']):
                pi,ri=map(int,s['pointers'][out_slot]);
                if ri!=req_slot or not 0<=pi<len(f['active']) or not f['active'][pi]:continue
                key=tuple(map(int,f['pointers'][pi]));witness=(*key,ri)
                r2['probe_wrong_twin']+=int(key==sibling and witness not in result)
                if key==parent:
                    actual.append(tuple(f['rows'][pi])==made[parent] and tuple(s['rows'][out_slot])==result[(*parent,ri)])
            r2['probe_claims_exact']=int(actual==[True])
        r2['residual_reads_consistent'] = consistent_candidate_reads(stages[1],req)
        reports[0].append(r1);reports[1].append(r2)
    run2=totals(reports[1])
    consistent=[g for g in reports[1] if g['residual_reads_consistent'] and g['nonempty']]
    run2['consistent_residual_nonempty_graphs']=len(consistent)
    run2['consistent_residual_nonempty_complete_graphs']=sum(g['complete'] for g in consistent)
    return dict(run1=totals(reports[0]),run2=run2,
                both_complete_graphs=sum(a['complete'] and b['complete'] for a,b in zip(*reports)))
