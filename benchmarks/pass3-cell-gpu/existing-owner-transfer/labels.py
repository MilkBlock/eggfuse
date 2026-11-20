"""Extract action-level reward labels from actual allocations and retained source identities."""
import argparse
import json
from pathlib import Path


def extract(result):
    out={};complete={}
    for case,arms in result.items():
        summary={};events={}
        for arm,r in arms.items():
            v=dict(source_runs=r['runs'],per_run_domain=r['domain'],admissible_run_count=r['natural_candidate_runs'],ordered_source_sha=r['source_check_digest'],
                   final_graph=r['graph'],later_source_unions=r['post_action_unions'],later_reads=r['following_reads'],later_read_hash=r['read_digest'])
            block=[i for i in r['events'] if i['event']['kind']=='existing_pair']
            if block:
                x=block[0];e=x['event'];assert e['old']==e['new']
                v.update(dict(action_run=x['source_run'],shape=e['shape'],issued_epoch=e['old_epoch'],source_templates=e['member_source_templates'],
                              old_members=e['old_members'],new_members=e['new_members'],previous_owners=[e['left_owner'],e['right_owner']],destination=e['destination'],
                              old_frame_birth_epochs=e['member_birth_epochs'],retired_owners=e['retired_owner_ids'],effect=e['outcome'],
                              old_external_reader_count=len(e['old']['external_readers']),old_live_refs=len(e['old']['old_refs'])))
                # Owner vector entries can become empty tombstones; charge actual live allocator delta independently.
                v['live_owner_credit']=e['old_charge'][0]-e['new_charge'][0]
                v['owner_vector_slots_freed']=e['old_charge'][1]-e['new_charge'][1]
                v['source_descriptors_freed']=e['old_charge'][2]-e['new_charge'][2]
                v['component_storage_delta']=e['old_charge'][-1]-e['new_charge'][-1]
                if e['allocation']:
                    before,after=e['allocation']
                    v.update(net_live_byte_credit=before[0]-after[0],new_bytes=after[1]-before[1],freed_bytes=after[2]-before[2],
                             peak_extra_requested_bytes=after[3]-before[0])
                    assert v['freed_bytes']-v['new_bytes']==v['net_live_byte_credit']
                if r['probe']:
                    v['controlled_union']=r['probe']['effect']
                    v['injected_controls']=r['controlled_union_attempts']
                    if 'graph' in r['probe']:
                        v['repaired_graph']=r['probe']['graph']
                        v['post_union_external_readers']=len(r['probe']['read']['external_readers'])
                # The full signed cell/slot references and chronology are preserved for one positive and both controls.
                if arm in ('split-merge-pooled','split-partial-pooled','split-stale-pooled','split-merge-probe-pooled'):
                    events[arm]={'seed':r['events'][0],'action':x,'post_union':r['probe']}
            v['credited_to_model']=False
            summary[arm]=v
        out[case]=summary;complete[case]=events
    return out,complete

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('dest',type=Path);a=p.parse_args()
    summary,complete=extract(json.loads((a.run/'results.json').read_bytes()))
    for name,data in [('results',summary),('examples',complete)]:
        (a.dest/(name+'.json')).write_text(json.dumps(data,indent=1)+'\n')
