"""Recompute live-owner, allocator, source identity and controlled union claims."""
from pathlib import Path
import json

base=Path(__file__).resolve().parent
def load(name):return json.loads((base/name).read_bytes())
v=load('results.json');examples=load('examples.json');unbaked=load('unbaked-census.json')
for name,r in v.items():
    gold=r['census-pooled'];keep=r['split-keep-pooled'];merged=r['split-merge-pooled']
    assert merged['live_owner_credit']==1 and merged['owner_vector_slots_freed']==merged['source_descriptors_freed']==0
    assert merged['effect']['added']==0 and merged['effect']['merged']==1
    assert len(set(merged['previous_owners']))==2 and len({owner for _,owner in merged['new_members']})==1
    assert merged['retired_owners']==[merged['previous_owners'][1]] and merged['destination']==merged['previous_owners'][0]
    assert merged['old_members']==keep['old_members']
    assert merged['net_live_byte_credit']==merged['freed_bytes']-merged['new_bytes'] and merged['peak_extra_requested_bytes']>0
    assert merged['later_reads'] and merged['later_source_unions'] and merged['old_external_reader_count'] and merged['old_live_refs']
    for arm in ('split-keep-pooled','split-merge-pooled','split-partial-pooled','split-stale-pooled'):
        q=r[arm]
        assert q['final_graph']==gold['final_graph'] and q['ordered_source_sha']==gold['ordered_source_sha']
        assert q['later_read_hash']==keep['later_read_hash'] and q['credited_to_model'] is False
    stale=r['split-stale-pooled'];partial=r['split-partial-pooled']
    assert stale['effect']['offered_epoch']!=stale['issued_epoch'] and stale['effect']['rejected']=='epoch'
    assert partial['effect']['rejected']=='incomplete_old_group'
    assert set(partial['effect']['offered']) < {i for i,_ in keep['old_members']}
    assert stale['new_members']==partial['new_members']==keep['old_members']
    full=examples[name]['split-merge-pooled']
    assert full['seed']['source_run']<full['action']['source_run']
    assert full['action']['event']['old']==full['action']['event']['new']
    for x in full['action']['event']['old']['old_refs']:assert 'ref' in x and 'epoch' in x
    probe=r['split-merge-probe-pooled']
    assert probe['controlled_union']==r['split-keep-probe-pooled']['controlled_union']
    if name in unbaked:
        assert unbaked[name]['census-pooled']['domain'][1]==0 and gold['per_run_domain'][-2]>0 and not gold['admissible_run_count']
        assert gold['final_graph']==unbaked[name]['census-pooled']['graph']
        assert merged['net_live_byte_credit']>0
        attempts=probe['injected_controls']
        assert attempts==r['split-keep-probe-pooled']['injected_controls']
        assert attempts[-1]['exhausted_candidates']==len(attempts)-1
        assert all(x.get('rejected_by_source') for x in attempts[:-1])
    else:
        assert merged['net_live_byte_credit']<0
        assert probe['controlled_union']['union_delta']>0 and len(set(probe['controlled_union']['previous_owners']))==2
        assert probe['repaired_graph']==r['split-keep-probe-pooled']['repaired_graph']
print('Verified three native existing-owner interventions, source digests, post-union readers, two failure controls, natural eligibility and allocator deltas.')
