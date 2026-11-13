"""Stable Cell token roles across compiler-only constructor-set lowering."""
import numpy as np
from multi_entry_ridge import template as raw_template,neighborhood_template as raw_neighborhood


def semantic(rule):
    layout=rule.get('token_layout')
    if layout is None:return rule,list(range(len(rule['slots'])))
    source=layout['rule'];projection=layout['slot_projection'];n=len(source['slots'])
    if source['query']!=rule['query'] or rule['slots'][:n]!=source['slots'] or projection[:n]!=list(range(n)) or len(projection)!=len(rule['slots']):raise ValueError('invalid semantic slot prefix')
    unions={frozenset(a['slot'] for a in o['args']) for o in rule['effects'] if o['kind']=='union' and all('slot' in a for a in o['args'])}
    for i,j in enumerate(projection[n:],n):
        if not 0<=j<n or rule['slots'][i]['sort']!=source['slots'][j]['sort'] or frozenset((i,j)) not in unions:raise ValueError('unproved temporary alias')
    # A semantic header cannot hide arbitrary new effects behind a valid alias.
    cursor=0;temp=n
    for op in source['effects']:
        if op['kind']=='set' and temp<len(projection) and cursor<len(rule['effects']) and rule['effects'][cursor].get('dst')==temp:
            value=op['value'];sort=source['slots'][value['slot']]['sort']
            expected=[dict(kind='construct',op='let',call=op['call'],args=op['args'],dst=temp,sort=sort),dict(kind='union',op='union',args=[dict(slot=temp),value])]
            if rule['effects'][cursor:cursor+2]!=expected or projection[temp]!=value['slot']:raise ValueError('semantic lowering mismatch')
            cursor+=2;temp+=1
        else:
            if cursor>=len(rule['effects']) or rule['effects'][cursor]!=op:raise ValueError('semantic effect mismatch')
            cursor+=1
    if cursor!=len(rule['effects']) or temp!=len(projection):raise ValueError('uncovered semantic effects')
    return source,projection


def template(rule):
    source,p=semantic(rule);roles,q=raw_template(source)
    return roles[p],q


def neighborhood_template(rule,rounds=2):
    source,p=semantic(rule);roles,q=raw_neighborhood(source,rounds)
    return roles[p],q


def token_required(rule):
    source,_=semantic(rule)
    return np.arange(len(rule['slots']))<len(source['slots'])
