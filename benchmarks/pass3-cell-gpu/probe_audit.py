"""Independent oracle for a typed e-graph ingress, including shared-class references."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path

import numpy as np
from codec import canonical,members


def replay(program,packet,normal,merged,join):
    raw=json.loads(program.read_text())['initial'];p=json.loads(packet.read_text())
    decoded=list(members(p));raw_counts=Counter(map(canonical,raw))
    assert raw_counts==Counter(canonical(row) for _,_,row in decoded)
    origins=defaultdict(list);changed=0;ordered_edges=0
    a,b=join
    assert p['symbols'][a]['sort']==p['symbols'][b]['sort'] and all('eq' in p['symbols'][k] for k in (a,b)) and a!=b
    with np.load(normal) as z,np.load(merged) as after:
        assert not z['union_accepted'].item() and after['union_accepted'].item()
        for k in ('selected','refs','table','hidden','role','raw'):np.testing.assert_array_equal(z[k],after[k])
        np.testing.assert_array_equal(z['selected'],np.arange(len(p['instances'])))
        rebuilt=[]
        for j,(cell,op,row) in enumerate(decoded):
            assert z['refs'][j].tolist()==[cell,op]
            td=p['tables'][int(z['table'][j])];n=len(row['values'])
            assert z['role'][j].tolist()==[n-1,*range(n-1),*([-1]*(len(z['role'][j])-n))]
            ids=z['raw'][j];cols=[*ids[1:n],ids[0]]
            recreated=dict(table=td['name'],subsumed=bool(z['hidden'][j]),values=[p['symbols'][k] for k in cols])
            rebuilt.append(recreated);ordered_edges+=n-1
            origins[int(ids[0])].append((cell,op,td['name']))
            pred=np.where(ids==max(join),min(join),ids)
            np.testing.assert_array_equal(after['current'][j],pred)
            changed+=int((pred!=ids).sum())
        assert raw_counts==Counter(map(canonical,rebuilt))
    return dict(rows=len(raw),ordered_arguments=ordered_edges,multi_member=sum(len(p['templates'][i])>1 for i,_,_ in p['instances']),
                instances=len(p['instances']),templates=len(p['templates']),unknown_original_writer=True,uncovered=0,
                ambiguous_result_classes=[dict(initial=p['symbols'][k],members=v) for k,v in origins.items() if len(v)>1],
                union_classes=[p['symbols'][k] for k in join],changed_port_resolutions=changed,roundtrip_exact=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('program','packet','normal','merged','out'):p.add_argument(k,type=Path)
    p.add_argument('--union',type=int,nargs=2,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(replay(a.program,a.packet,a.normal,a.merged,a.union),indent=1)+'\n')
