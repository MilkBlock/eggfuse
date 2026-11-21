"""Alpha-normalized, table-parameterized sealed query shapes and source-only deployment."""
import hashlib,json


def shapes(program,plans):
    rules=program['recipe']['rules']
    if len(rules)!=len(plans):raise ValueError("different rule counts")
    out=[]
    for rule,plan in zip(rules,plans):
        if not plan or not all(plan['linked'][1:]):
            out.append(None);continue
        slots={};tables={};ops=[];parents=queries=primitives=literals=links=result_checks=key_fields=0
        for atom,pick,_ in plan['ins']:
            a=rule['query'][atom];call=a['call'];args=[];seen=set(slots)
            if 'table' in call:
                tag=['table',tables.setdefault(call['table'],len(tables))]
                if pick:parents+=1
                else:queries+=1
            else:tag=['primitive',call['primitive'],call.get('output')];primitives+=1
            for arg in a['args']:
                if 'slot' in arg:
                    s=arg['slot'];args.append(['slot',slots.setdefault(s,len(slots)),rule['slots'][s]['sort']['kind']])
                else:args.append(['literal',arg]);literals+=1
            if pick:links+=sum(1 for v in a['args'] if v.get('slot') in seen)
            else:
                key_fields+=len(args)-1
                result_checks+=int(a['args'][-1].get('slot') in seen or 'slot' not in a['args'][-1])
            ops.append([int(pick),tag,args])
        signature=json.dumps(ops,sort_keys=True,separators=(',',':')).encode()
        x=[parents/8,queries/12,primitives/12,key_fields/48,len(slots)/32,links/24,literals/8,result_checks/16]
        out.append((hashlib.sha256(signature).hexdigest(),x))
    return out


def mask(rows,policy):
    selected=set(policy)
    return [v is not None and v[0] in selected for v in rows]

def predict(weights,x):
    """Apply a frozen return head once at plan load. It does not run during source search."""
    import math
    def dot(ws,bs,values):
        return [sum(a*b for a,b in zip(r,values))+offset for r,offset in zip(ws,bs)]
    data=dot(weights['0.weight'],weights['0.bias'],x)
    if '2.weight' in weights:
        data=dot(weights['2.weight'],weights['2.bias'],[math.tanh(v) for v in data])
    return data[0]


def deploy(rows,policy):
    if 'weights' not in policy:return policy['members']
    return {key for value in rows if value is not None for key,x in (value,) if predict(policy['weights'],x)>0}
