"""Serialize resolved device fields without computing a binding, union or continuation."""
import json
from pathlib import Path


def export(schema,tables,rows,meta,roots,strings,set_members=()):
    encoded=[]
    for row,m in zip(rows,meta):
        if m[3]==2:continue
        name,columns=tables[int(m[0])]
        values=[]
        for v,column in zip(row,columns):
            sort,kind=column[:2]
            n=int(v)
            if kind=='eq':values.append({'sort':sort,'eq':f'Cell({n})'})
            elif kind=='set':
                ids=sorted(int(roots[int(raw)]) for i,raw in enumerate(set_members) if n & (1<<i))
                if len(ids)!=len(set(ids)):raise ValueError('device emitted duplicate canonical set members')
                values.append({'sort':sort,'elements':[{'sort':column[2],'eq':f'Cell({x})'} for x in ids]})
            elif kind=='String':values.append({'sort':sort,'value':strings[n]})
            elif kind in ('i64','Unit','bool','f64'):values.append({'sort':sort,'value':bool(n) if kind=='bool' else n})
            else:raise ValueError(f'unsupported exported {sort} ({kind})')
        encoded.append({'table':name,'subsumed':bool(m[3]),'values':values})
    return {'rows':encoded,'anchors':[dict(sort=s,old=old,now=f'Cell({int(roots[rank])})')
                                      for s,old,rank in schema['anchors']]}


def schema_for(packet):
    return dict(tables=[[t['name'],[(s['name'],s['kind'],s['element']['name']) if s['kind']=='set' else (s['name'],s['kind']) for s in t['schema']]] for t in packet['tables']],
                anchors=[[v['sort'],v['eq'],rank] for v,rank in zip(packet['symbols'],packet['eq_order']) if 'eq' in v])
