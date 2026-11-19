"""Check every counterfactual against the replay and freeze the input/target hashes."""
from collections import Counter
from hashlib import sha256
import argparse,json
from pathlib import Path
import numpy as np
from source import dataset, STATES
from check import audit_graph
from runtime import CORPUS


def gold(d):
    a,b=d['target1'][:,::-1],d['target2']
    first,second=({k:np.array(v,copy=True) for k,v in [('active',t[...,0]),('pointers',t[...,1:3]),('rows',t[...,3:])]} for t in (a,b))
    second['pointers'][...,0]=7-second['pointers'][...,0]
    return first,second


def verify_groups(d):
    size=len(d['a']);base=np.arange(size)//8*8
    for name in ('a','b','a_port'):
        np.testing.assert_array_equal(d[name],d[name][base]);
    # State varies across the same dynamic source graph/Request; only the origin
    # of one Request changes across variants. Query handles remain identical.
    by_variant=base+np.arange(size)%2
    for name in ('requests','request_ports','probe_kind'):
        np.testing.assert_array_equal(d[name],d[name][by_variant]);
    req=d['requests'];delta=req[::2]!=req[1::2];assert (delta[:,:,3].sum(1)==1).all()
    assert not delta[:,:,[0,1,2,4]].any()
    changed=delta[:,:,3];assert (d['probe_kind'][::2][changed]==2).all()
    assert np.all(d['external'][d['state']!=3]==0)
    assert all(np.all(d[name]>=0) and np.all(d[name]<=7) for name in ('a','b','requests','external','target1','target2'))


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args()
    templates=json.loads((CORPUS/'manifest.json').read_text())['templates']
    signatures={part:{t['family_id'] for t in templates if t['split']==part} for part in ('train','heldout')}
    assert signatures['train'].isdisjoint(signatures['heldout'])
    reports={};blind_inputs={};blind_truth={};events_seen=set()
    for t in templates:
        reports[t['id']]={}
        for split in (('train','test') if t['split']=='train' else ('test',)):
            d=dataset(split,t);verify_groups(d);f,s=gold(d);states={};events=set()
            for i,state_idx in enumerate(d['state']):
                r1,r2,legal,event=audit_graph(d,i,f,s);events.add(event)
                assert r1['complete'] and r2['complete'] and r1['obligations']==6 and r2['nonempty']
                np.testing.assert_array_equal(legal,d['request_legal'][i]);assert sum(legal)==int(d['target2'][i,:,0].sum())
                count=states.setdefault(STATES[state_idx],Counter());count['graphs']+=1;count['nonempty']+=r2['nonempty'];count['obligations']+=r2['obligations']
                count['secondary_event_graphs']+=int(r2['secondary_event']);count['secondary_obligations']+=r2['secondary_obligations'];count['pending_local_requests']+=r2['pending_conditional_requests']
            complete={state:dict(c) for state,c in states.items()}
            assert all(c['graphs']==len(d['a'])//4 for c in complete.values())
            assert sum('external-' in e for e in events)==9,(t['id'],events)
            events_seen.update(events)
            ix=d['blind'].astype(bool);key=('a','b','requests','external','phase','committed','state','variant','probe_kind')
            hashes={k:sha256(d[k][ix].tobytes()).hexdigest() for k in key}
            if split in blind_inputs:assert hashes==blind_inputs[split]
            blind_inputs[split]=hashes
            if split=='test':blind_truth[t['id']]=d['request_legal'][ix]
            reports[t['id']][split]=dict(graphs=len(ix),blind_graphs=int(ix.sum()),state_counts=complete,replay_events=sorted(events),
                sha256={k:sha256(v.tobytes()).hexdigest() for k,v in d.items() if isinstance(v,np.ndarray)})
    contrast={}
    for key,a in blind_truth.items():
        contrast[key]={other:int((a!=b).any(1).sum()) for other,b in blind_truth.items() if other!=key}
    assert any(any(c.values()) for c in contrast.values())
    result=dict(schema='eggfuse.eclass-ablation.data/v1',family_counts={k:len(v) for k,v in signatures.items()},
                train_test_family_overlap=0,blind_raw_input_hashes=blind_inputs,blind_shared_raw_per_template_changed_legality=contrast,
                sources={name:sha256((CORPUS/name).read_bytes()).hexdigest() for name in ('manifest.json','replay-evidence.json','extra-events.json')},
                generator={x:sha256((Path(__file__).parent/x).read_bytes()).hexdigest() for x in ('source.py','runtime.py','check.py')},
                replay_events=len(events_seen),panels=reports)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    for part in ('train','heldout'):
        for split in ('train','test'):
            chosen=[reports[t['id']][split] for t in templates if t['split']==part and split in reports[t['id']]]
            print(part,split,'graphs',sum(d['graphs'] for d in chosen),'blind',sum(d['blind_graphs'] for d in chosen),
                  'secondary_obligations',sum(sum(c['secondary_obligations'] for c in d['state_counts'].values()) for d in chosen))

if __name__=='__main__':main()
