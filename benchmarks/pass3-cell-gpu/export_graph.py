"""Serialize resolved device fields without computing a binding, union or continuation."""
import json
from pathlib import Path


def export(schema,tables,rows,meta,roots,strings):
    encoded=[]
    for row,m in zip(rows,meta):
        if m[3]==2:continue
        name,columns=tables[int(m[0])]
        values=[]
        for v,(sort,kind) in zip(row,columns):
            n=int(v)
            if kind=='eq':values.append({'sort':sort,'eq':f'Cell({n})'})
            elif kind=='String':values.append({'sort':sort,'value':strings[n]})
            elif kind in ('i64','Unit','bool','f64'):values.append({'sort':sort,'value':bool(n) if kind=='bool' else n})
            else:raise ValueError(f'unsupported exported {sort} ({kind})')
        encoded.append({'table':name,'subsumed':bool(m[3]),'values':values})
    return {'rows':encoded,'anchors':[dict(sort=s,old=old,now=f'Cell({int(roots[rank])})')
                                      for s,old,rank in schema['anchors']]}


def schema_for(packet):
    return dict(tables=[[t['name'],[(s['name'],s['kind']) for s in t['schema']]] for t in packet['tables']],
                anchors=[[v['sort'],v['eq'],rank] for v,rank in zip(packet['symbols'],packet['eq_order']) if 'eq' in v])
