"""Best budgeted routing of the reference-winning parent tuples on this layout."""
from collections import defaultdict
import json


def reference_ceiling(tickets, plans, budget):
    roots=defaultdict(dict)
    for t in tickets:
        node=roots[t['run'],t['rule']]
        plan=plans[t['rule']]
        for i,(w,page) in enumerate(zip(t['anchors'],t['audit_pages'],strict=True)):
            address=json.dumps(w,sort_keys=True)
            key=(page if plan['ins'][i][2] else None,address)
            node=node.setdefault(key,{})
        node['wins']=node.get('wins',0)+1

    def best(node):
        scores=defaultdict(int)
        for key,child in node.items():
            if key!='wins':
                page,_=key
                scores[page]+=best(child)
        unbudgeted=scores.pop(None,0)
        return unbudgeted+sum(sorted(scores.values(),reverse=True)[:budget])+node.get('wins',0)
    return sum(best(tree) for tree in roots.values())
