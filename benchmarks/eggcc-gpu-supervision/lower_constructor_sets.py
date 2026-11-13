"""Lower constructor assignment into existing construct/union Cell instructions.

A temporary Eq slot/ID is charged explicitly. Ordinary mutable functions,
literal operands and hidden-row reuse are not covered by this lowering.
"""
from copy import deepcopy


def lower(recipe):
    out=deepcopy(recipe);tables={t['name']:t for t in recipe['tables']};sites=[]
    for rid,rule in enumerate(out['rules']):
        effects=[];semantic_rule={k:deepcopy(rule[k]) for k in ('slots','query','effects')};projection=list(range(len(rule['slots'])))
        for oi,op in enumerate(rule['effects']):
            table=tables.get(op.get('call',{}).get('table'))
            if op['kind']!='set' or table is None or table['kind']!='constructor':effects.append(op);continue
            schema=table['schema'];args=op['args'];value=op['value']
            if any('slot' not in x for x in [*args,value]):raise ValueError('constructor set requires slot operands')
            if len(args)+1!=len(schema) or schema[-1]['kind']!='eq':raise ValueError('constructor set schema')
            for operand,sort in zip([*args,value],schema):
                slot=operand['slot']
                if not 0<=slot<len(rule['slots']) or rule['slots'][slot]['sort']!=sort:raise ValueError('constructor set sort')
            projection.append(value['slot'])
            temp=len(rule['slots']);rule['slots'].append(dict(sort=deepcopy(schema[-1]),definition='effect'))
            sites.append(dict(rule=rid,source_operation=oi,lowered_operation=len(effects),temporary_slot=temp))
            effects.extend([dict(kind='construct',op='let',call=op['call'],args=args,dst=temp,sort=deepcopy(schema[-1])),
                dict(kind='union',op='union',args=[dict(slot=temp),value])])
        rule['effects']=effects
        if len(rule['slots'])!=len(semantic_rule['slots']):rule['token_layout']=dict(rule=semantic_rule,slot_projection=projection)
    return out,sites
