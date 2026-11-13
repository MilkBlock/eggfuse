"""Complete a consumer from its producer's settled template context."""
import json
from cell_token_successors import complete_template,continuation_contract


def compile_context(recipe,edge):
    rules=recipe['rules'];source=rules[edge['producer']];target=rules[edge['consumer']]
    tables={t['name']:t for t in recipe['tables']}
    facts,blocked=complete_template(source,tables)
    if blocked:return dict(covered=False,reason='unsupported_source')
    contract=continuation_contract(source,target,facts,edge)
    if contract!=edge['contract']:raise ValueError('stale continuation contract')
    env={slot:tuple(ref) for slot,ref in edge['inputs']}
    known={(table,tuple(args[:-1])):args[-1] for table,args,_ in facts}
    reused=0
    def arg(a):
        return env[a['slot']] if 'slot' in a else ('literal',json.dumps(a,sort_keys=True))
    def blocked(reason,operation):return dict(covered=False,reason=reason,operation=operation,reused_prefix=reused)
    for i,op in enumerate(target['effects']):
        kind=op['kind']
        if kind=='copy':env[op['dst']]=arg(op['arg'])
        elif kind=='construct':
            table=op['call'].get('table');key=(table,tuple(arg(a) for a in op['args']))
            if tables.get(table,{}).get('kind')!='constructor' or key not in known:
                return blocked('new_constructor_or_external_witness',i)
            env[op['dst']]=known[key];reused+=1
        elif kind=='union':
            if len(op['args'])!=2 or arg(op['args'][0])!=arg(op['args'][1]):return blocked('new_equality',i)
        else:return blocked('ordered_or_scalar_effect:'+kind,i)
    projection={}
    for dst,ref in env.items():
        if ref[0]=='input':
            src=ref[1]
            # This path reads final source slots, not a second initial-binding copy.
            if any(op.get('dst')==src for op in source['effects']):return blocked('overwritten_source_input',len(target['effects']))
        elif ref[0]=='result':
            opid=ref[1];op=source['effects'][opid]
            if op['kind']!='construct':raise ValueError('result is not constructor')
            src=op['dst']
            if any(later.get('dst')==src for later in source['effects'][opid+1:]):return blocked('overwritten_source_result',len(target['effects']))
        else:return blocked('literal_slot_value',len(target['effects']))
        if source['slots'][src]['sort']!=target['slots'][dst]['sort']:raise ValueError('context result sort mismatch')
        projection[dst]=src
    return dict(covered=True,projection=projection,reused_constructors=reused,
                ownership_transfer_authorized=False)
