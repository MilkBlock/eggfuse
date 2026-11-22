"""Audit imports and exports against all actual matched witnesses, including residual consumers."""
from collections import defaultdict
import numpy as np


def boundaries(targets, publications, witnesses):
    produced = defaultdict(list)
    uses = defaultdict(list)
    for ticket, (ordinal, effect, row, table) in enumerate(publications, 1):
        produced[int(ordinal)].append(ticket)
    for event, atom in np.argwhere(witnesses[:,:,2]>0):
        row, version, ticket = map(int,witnesses[event,atom])
        # Repair can copy an anchor to the surviving physical row. The
        # observed ticket identifies the original return across that transfer.
        if row<=0 or ticket>len(publications) or publications[ticket-1,0] >= event+1:
            raise ValueError("consumer and returned witness disagree")
        uses[ticket].append((int(event+1),int(atom)))
    imports, exports, consumers = [], [], []
    for index,target in enumerate(targets):
        path=list(map(int,target[5:5+target[4]]))
        members=set(path)
        for ordinal in path:
            for pos,(address,epoch,ticket) in enumerate(witnesses[ordinal-1]):
                if address and (not ticket or int(publications[ticket-1,0]) not in members):
                    imports.append((index,ordinal,pos,address-1,epoch,ticket))
            for ticket in produced[ordinal]:
                # Include ports with no currently observed consumer: later Runs may use them.
                exports.append((index,ticket))
                consumers.extend((index,ticket,event,atom) for event,atom in uses[ticket] if event not in members)
    def array(rows,width):
        return np.asarray(rows,dtype=np.int32).reshape(-1,width)
    return dict(imports=array(imports,6),exports=array(exports,2),outside_uses=array(consumers,4))
