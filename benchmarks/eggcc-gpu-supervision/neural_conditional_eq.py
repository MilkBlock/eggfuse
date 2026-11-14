"""Bake typed input partitions into positive completion proofs.

The GPU selects an already compiled case from existing query incidence. This is
an exact proof side channel, not learned floating inference. It neither executes
RHS effects nor establishes matching, visibility, or external constructor reuse.
"""
import numpy as np
from neural_baked_eq import partition,compile_rule


def compile_cases(recipe,rule,width,atoms=2,fields=5,limit=4096):
    base=compile_rule(recipe,rule,width)
    origins={}
    for a,atom in enumerate(rule['query']):
        if a>=atoms or len(atom['args'])>fields:raise ValueError('query incidence capacity')
        for f,arg in enumerate(atom['args']):origins.setdefault(arg['slot'],a*fields+f)
    inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
    if set(inputs)!=set(origins):raise ValueError('incomplete input incidence')
    sorts=[rule['slots'][i]['sort'] for i in inputs]
    pairs=[(a,b) for a in range(len(inputs)) for b in range(a+1,len(inputs)) if sorts[a]==sorts[b]]
    cols=np.array([origins[inputs[a]]*(atoms*fields)+origins[inputs[b]] for a,b in pairs],np.int32)
    def fallback(reason):
        return dict(relation_width=2*(atoms*fields)**2,columns=cols,signatures=np.zeros((0,len(pairs)),bool),known=np.zeros((0,len(base['known'])),bool),base=base['known'],supported=False,reason=reason)
    if not base['supported']:return fallback(base['reason'])
    assignments=[]
    def visit(labels):
        if len(assignments)>limit:return
        i=len(labels)
        if i==len(inputs):assignments.append(labels);return
        groups=sorted(set(labels))
        for g in groups:
            if sorts[labels.index(g)]==sorts[i]:visit(labels+[g])
        visit(labels+[max(groups,default=-1)+1])
    visit([])
    if len(assignments)>limit:return fallback('input partition budget exceeded')
    signatures=[];proofs=[];oi,oj=np.triu_indices(width,1);n=len(rule['slots'])
    for labels in assignments:
        signature=np.array([labels[a]==labels[b] for a,b in pairs],bool)
        roots=partition(recipe,rule,[(inputs[a],inputs[b]) for (a,b),same in zip(pairs,signature) if same])
        known=np.array([j<n and rule['slots'][i]['sort']['kind']=='eq' and rule['slots'][i]['sort']==rule['slots'][j]['sort'] and roots[i]==roots[j] for i,j in zip(oi,oj)],bool)
        signatures.append(signature);proofs.append(known)
    return dict(relation_width=2*(atoms*fields)**2,columns=cols,signatures=np.array(signatures),known=np.array(proofs),base=base['known'],supported=True,reason='typed input partitions')


def select(plan,relations,xp):
    if relations.shape[1]!=plan['relation_width']:raise ValueError('query incidence layout mismatch')
    values=relations[:,plan['columns']]
    valid=xp.all(xp.isfinite(values)&((values==0)|(values==1)),axis=1)
    same=xp.all((values[:,None,:]>0)==plan['signatures'][None,:,:],axis=-1)&valid[:,None]
    known=xp.any(same[:,:,None]&plan['known'][None,:,:],axis=1)
    # Empty/unsupported catalogs retain only unconditional proof; no negative
    # consequences are invented. Callers still audit the complete output mask.
    return known|plan['base'][None,:],xp.sum(same.astype(xp.int32),axis=1)==1
