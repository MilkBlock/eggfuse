"""Offline lookup of a real CPU partition, rebinding physical ports to raw handles."""
from functools import lru_cache
from pathlib import Path
import json

CORPUS=Path(__file__).resolve().parents[1]/'corpus'


@lru_cache(maxsize=1)
def archives():
    basic=json.loads((CORPUS/'replay-evidence.json').read_text())
    extended=json.loads((CORPUS/'extra-events.json').read_text())
    main={row['id']:row for row in basic}
    extra={row['id']:row for row in extended['cases']}
    external={}
    for row in extra.values():
        if row['external_endpoints'] is not None:
            identifier=row['id'].split('-')[0]
            first,second=row['external_endpoints']
            external[(identifier,first,second-16)]=row
    return main,extra,external


def partition_record(template,a,a_port,phase,committed,external):
    main,extra,edges=archives();identifier='r'+template['id'].split('-')[-1]
    by_raw={(int(row[0]),int(row[1])):int(port) for row,port in zip(a,a_port)}
    if external[0]:
        if list(phase)!=[1,1] or list(committed)!=[1,1]:raise ValueError('uncertified external event order')
        o,h,p,k=map(int,external[1:]);
        if o==p:raise ValueError('external event must cross owners')
        event=edges[identifier,by_raw[o,h],by_raw[p,k]]
        groups=event['equal_groups'];secondary=event['secondary_congruence'];order=(o,p)
    elif list(phase)==[0,0] and list(committed)==[0,0]:
        event=main[identifier+'-enabled'];groups=event['pre_sort_partition'];secondary=[];order=(0,1)
    elif list(phase)==[1,1] and list(committed)==[1,1]:
        event=main[identifier+'-enabled'];groups=event['post_sort_partition'];secondary=[];order=(0,1)
    elif list(phase)==[1,1] and int(sum(committed))==1:
        suppressed=next(i for i,c in enumerate(committed) if not c)
        event=extra[identifier+'-only-second'];groups=event['equal_groups'];secondary=[];order=(suppressed,1-suppressed)
    else:raise ValueError('no independently verified CPU record for this phase/receipt state')
    lookup={16*order.index(o)+port:(o,h) for (o,h),port in by_raw.items()}
    partition={}
    for group in groups:
        visible={lookup[s] for s in group if s in lookup}
        for member in visible:partition[member]=visible
    if set(partition)!=set(by_raw):raise ValueError('archived CPU partition omitted a public endpoint')
    extra_edges=[(lookup[x],lookup[y]) for x,y in secondary if x in lookup and y in lookup]
    if len(extra_edges)!=len(secondary):raise ValueError('secondary edge is not in the selected public interface')
    return partition,extra_edges,event['id']
