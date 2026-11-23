"""Freeze weights; replace exactly one teacher Run and submit its model proofs to native verification."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import torch
from actor import InstructionActor
from catalog import Catalog
from history import History
from online import propose


@torch.no_grad()
def study(root,binary,weights,seed, field_pointer=False):
    torch.set_num_threads(1)
    actor=InstructionActor(field_pointer=field_pointer).eval()
    actor.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True))
    manifest=json.loads((root/'manifest.json').read_bytes())
    results=[]
    with TemporaryDirectory() as temp:
        tape_path=Path(temp)/'trial.json'
        for rec in manifest:
            if rec['split']=='train':
                continue
            folder=root/rec['directory']
            program=folder/'program.json'
            tape=json.loads((folder/'tape.json').read_bytes())
            cat=Catalog(json.loads(program.read_bytes()))
            history=History(cat,seed+rec['seed'])
            nodes=actor.template_graph(cat)
            for line in (folder/'memory.jsonl').read_text().splitlines():
                frame=json.loads(line)
                snapshot=history.snapshot(frame)
                run=snapshot.run
                network=propose(actor,cat,snapshot,nodes)
                prefix=[r for r in tape['requests'] if r['run']<run]
                expected=[r for r in tape['requests'] if r['run']==run]
                lookup={p.address:p for p in snapshot.ports}
                first=max(r['token'] for r in tape['requests'])+1
                packets=[]
                for i,(rule,refs) in enumerate(network):
                    parents=[dict(address=dict(token=history.inverse[t],op=pc),version=lookup[t,pc].version)
                             for t,pc in refs]
                    packets.append(dict(token=first+i,rule=rule,parents=parents,run=run))
                def verify(suffix):
                    tape_path.write_text(json.dumps({**tape,'requests':prefix+suffix}))
                    return json.loads(subprocess.check_output([binary,'replay',program,tape_path,'time',str(run)]))
                replay=verify(packets)
                counts=replay['counts']
                if not counts['calls'] or replay['unused'] or counts['accepted']<len(prefix):
                    raise ValueError('prefix failed native verification')
                # Individually verify model proposals using event inputs. Reference
                # completeness counts unique complete, signed tuples only.
                def key(r):
                    return (r['rule'],tuple((p['address']['token'],p['address']['op'],p['version']) for p in r['parents']))
                event_ids={e['token'] for e in frame['repair_events']}
                refs_event=lambda r:any(p['address']['token'] in event_ids for p in r['parents'])
                needed={key(r) for r in expected if refs_event(r)}
                accepted_event=set()
                for p in packets:
                    if refs_event(p) and verify([p])['counts']['accepted']==len(prefix)+1:
                        accepted_event.add(key(p))
                # This diagnostic is unambiguous only when the reference supplies
                # one tuple. Compare identities, never assume a particular rule shape.
                collapsed = 0
                if len(expected)==1:
                    target=key(expected[0])
                    for packet in packets:
                        rid,parents=key(packet)
                        if rid==target[0] and any(parents[i][:2]==parents[j][:2]
                            and target[1][i][:2]!=target[1][j][:2]
                            for i in range(len(parents)) for j in range(i)):
                            collapsed+=1
                results.append(dict(distinct_parents_collapsed=collapsed,case=rec['directory'],split=rec['split'],collision=rec['collision'],run=run,
                    teacher_prefix_commits=len(prefix),reference_current=len(expected),network_issued=len(packets),
                    accepted_current=counts['accepted']-len(prefix),duplicates=counts['duplicates'],
                    rejected=counts['rejected'],addr_exact=len({key(r) for r in packets}&{key(r) for r in expected}),
                    actual_new_events=sum(e['run']==run for e in replay['runtime_events']),
                    reference_new_events=sum(e['run']==run for e in tape['repair_events']),
                    required_event_consumers=len(needed),verified_reference_event_consumers=len(accepted_event&needed)))
    return dict(field_pointer=field_pointer,mode='assist',assistance='exact signed prefix provided; only one Run per trial issued by frozen Actor',
                build_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                weights_file_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                independent_verifier_search_calls=0,results=results)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','receiver','weights','output'):
        ap.add_argument(name,type=Path)
    ap.add_argument('--field-pointer',action='store_true')
    a=ap.parse_args()
    a.output.write_text(json.dumps(study(a.corpus,a.receiver.resolve(),a.weights,1703,a.field_pointer),indent=2)+'\n')
