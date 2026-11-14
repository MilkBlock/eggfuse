"""Bake local constructor congruence into fixed Cell wiring.

Exact semantic control, not neural floating inference or global completeness.
No runtime reverse-dependency lists are built.
"""
import numpy as np
from typed_literal import compiled_id


def compile_conditions(recipe, rule, width):
    tables={t['name']:t['kind'] for t in recipe['tables']}
    facts=[]
    def fact(call,args,result):
        name=call.get('table')
        if tables.get(name)!='constructor':raise ValueError('local congruence requires constructor facts')
        if rule['slots'][result]['sort']['kind']!='eq':raise ValueError('constructor result must be Eq')
        encoded=[]
        for a in args:
            if set(a)=={'slot'}:
                if not 0<=a['slot']<len(rule['slots']):raise ValueError('invalid constructor slot')
                encoded.append((True,a['slot']))
            else:encoded.append((False,compiled_id(a,recipe)))
        facts.append((name,encoded,result))
    for atom in rule['query']:
        if not atom['args'] or set(atom['args'][-1])!={'slot'}:raise ValueError('constructor result slot required')
        fact(atom['call'],atom['args'][:-1],atom['args'][-1]['slot'])
    for op in rule['effects']:
        if op['kind']=='construct':fact(op['call'],op['args'],op['dst'])
        elif op['kind']=='set':
            if set(op['value'])!={'slot'}:raise ValueError('set result slot required')
            fact(op['call'],op['args'],op['value']['slot'])
        elif op['kind'] not in ('union','copy'):raise ValueError('unsupported local effect')
    pairs=[]
    for i,(name,args,result) in enumerate(facts):
        for other,inputs,target in facts[i+1:]:
            if name!=other or result==target:continue
            if len(args)!=len(inputs):raise ValueError('constructor arity mismatch')
            if rule['slots'][result]['sort']!=rule['slots'][target]['sort']:raise ValueError('constructor result sort mismatch')
            pairs.append((args,inputs,result,target))
    arity=max((len(a) for a,_,_,_ in pairs),default=0)
    n=len(pairs);left=np.zeros((n,arity),np.int32);right=left.copy()
    ls=np.zeros((n,arity),bool);rs=ls.copy();used=ls.copy();outputs=np.zeros((n,2),np.int32)
    for i,(a,b,u,v) in enumerate(pairs):
        outputs[i]=u,v
        for j,((sa,va),(sb,vb)) in enumerate(zip(a,b)):
            ls[i,j]=sa;rs[i,j]=sb;left[i,j]=va;right[i,j]=vb;used[i,j]=True
    return dict(left=left,right=right,left_slot=ls,right_slot=rs,used=used,outputs=outputs)


def activate(plan,labels,valid,xp):
    left=xp.array(plan['left']);right=xp.array(plan['right'])
    ls=xp.array(plan['left_slot']);rs=xp.array(plan['right_slot']);used=xp.array(plan['used'])
    a=xp.clip(left,0,len(labels)-1);b=xp.clip(right,0,len(labels)-1)
    lv=xp.where(ls,labels[a],left);rv=xp.where(rs,labels[b],right)
    readable=(~ls|valid[a])&(~rs|valid[b])
    active=xp.all(~used|(readable&(lv==rv)),axis=1)
    out=xp.array(plan['outputs']);positions=xp.arange(len(labels))
    active=active&valid[out[:,0]]&valid[out[:,1]]
    edges=xp.any(active[:,None,None]&(positions[None,:,None]==out[:,0,None,None])&
                 (positions[None,None,:]==out[:,1,None,None]),axis=0)
    return edges|edges.T
