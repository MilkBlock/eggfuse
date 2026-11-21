"""Verify the trusted archive, byte identities, source coordinates and native causal row transport."""
import json
from collections import Counter
from pathlib import Path
from bundle import sha,fingerprint,read,HERE
from region import Source,INPUT
def verify():
    ev=read(HERE/'evidence.json');blobs=read(HERE/'native-text.json');trust=read(HERE/'trust.json')
    assert sha((HERE/'evidence.json').read_bytes())==trust['manifest_sha256']
    assert ev['binary_sha256']==trust['binary_sha256']
    result=Counter();scope=Counter()
    for donor,d in ev['donors'].items():
        assert all(d['reference']['source_checks'].values()) and len(d['discovery']['generic'])==d['discovery']['generic_cap']
        assert sum(d['counts'].values())==d['discovery']['observed_edges']
        assert all(sha((INPUT/n).read_bytes())==h for n,h in d['source_parts'].items())
        source=Source(donor);original={(r['path'],r['line'],r['sha256']) for r in source.forms}
        for item in d['samples']:
            sid=item['sample_id'];signed=trust['samples'][sid];assert fingerprint(item)==signed['sample_sha256']
            def text(n):
                r=item['artifacts'][n];assert r['path']==f'samples/{sid}/{n}'
                raw=blobs[r['sha256']];assert sha(raw.encode())==r['sha256'];return raw
            local=lambda f:json.loads(text(f))
            for key in item['artifacts']:text(key)
            assert item['artifacts']['origin.json']['sha256']==signed['origin_sha256']
            origin=local('origin.json');s=origin['sample'];meta=origin['profile'];p=s['producer'];c=s['consumer']
            assert p['epoch']<c['epoch'] and c['epoch']-p['epoch']==item['relative_runs'] and p['ordinal']<c['ordinal']
            assert p['serial']==item['producer_serial'] and c['serial']==item['consumer_serial']
            f=s['original_fact'];r=next(v for v in c['rows'] if v['atom']==s['consumer_atom'])['named'];fact=r['row']['Fact']
            # Source atom indexes can include intervening scalar predicates.
            assert r['atom']==s['consumer_atom'] and (fact['cell']<<32|fact['op'])==f and r['version']==s['original_version']==p['epoch']
            assert s['birth_event'][4]==f and s['birth_event'][5][1]==p['rule'] and f&0xffffffff==item['producer_op']
            assert all((r['path'],r['line'],r['sha256']) in original for r in meta.get('source_rules',[]))
            ac=item['artifacts'].get('native/acceptance.json')
            if ac:
                assert ac['sha256']==signed['acceptance_sha256'];receipt=local('native/acceptance.json');assert receipt==item['native_acceptance']
                assert all(item['artifacts']['native/'+n]['sha256']==h for n,h in receipt['artifact_sha256'].items())
                assert item['artifacts']['entry.egg']['sha256']==receipt['artifact_sha256']['entry.egg']
            else:assert not item['native_accepted'] and signed['acceptance_sha256'] is None
            result['samples']+=1;scope[item['scope_mode']]+=1
            if not item['native_accepted']:continue
            result['accepted']+=1
            rep=local('native/ripen.json');g=local('native/saturated-rule-composition.json');h=local('native/history.json')
            assert rep['ripen']['state']=='Saturated' and rep['ripen']['updated'] is False and rep['native_stop_reason'] is None and rep['checks']=='passed'
            assert rep['saturated_rule_composition']['status']=='exported' and len(g['rows'])==rep['saturated_rule_composition']['facts']
            assert not g['scope'].get('observation_only') and len(g['values'])==len(g['local_ids'])==rep['saturated_rule_composition']['values']
            assert len(h['records'])==receipt['records'] and all(all(0<=j<i for j in rec['parents']) for i,rec in enumerate(h['records']))
            n=len(g['values']);assert all(all(0<=v<n for v in [*row['args'],row['result']]) for row in g['rows'])
            assert all(v is None or 0<=v<n for v in [token['final_class'] for token in h['tokens']])
            init=local('native/initial-state.json')
            assert len(item['seed_roots'])==len(meta['root_rows'])
            for row in item['seed_roots']:
                assert init['rows'][row['initial_row']]==dict(op=row['table'],args=row['argument_classes'],result=row['result_class'])
            bind=item['port_binding']
            if bind['eligible_full_edge']:
                assert bind['initial_output_row'] is None and bind['output_history_sites'] and bind['directed_native_reads']
                assert item['scope_mode'] in ('full','augmented') and bind['certified_producer_new_port']
                result['directed']+=1
            for link in bind.get('local_causal_edges',[]):
                src=h['records'][link['producer_index']];dst=h['records'][link['consumer_index']]
                assert src['id']==link['producer_record'] and dst['id']==link['consumer_record']
                assert link['producer_index'] in dst['parents'] and link['token'] in src['produced'] and link['token'] in dst['required']
                assert g['rows'][link['row']]['result']==link['read_result_class']
            for m in item.get('mapped_native_edges',[]):
                if not m.get('donor_receipt'):continue
                t=m['donor_receipt'];bf=t['fact'];assert t['producer_op']==m['producer_op']==bf&0xffffffff
                assert t['consumer_atom']==m['consumer_atom'] and t['birth_event'][4]==bf
                assert t['producer_epoch']==t['consumer_version']<t['consumer_epoch']
                assert (m['donor_join']=='same_producer')==(t['producer_serial']==item['producer_serial'])
                if not m['nominated']:result['extra_route_receipts']+=1
    assert len(trust['samples'])==result['samples'] and result['extra_route_receipts']>0 and result['directed']>0
    print('Verified real donor scope counts, original rules and fresh source identities, byte-bound native graphs and history, and directed write/read witnesses:',dict(result),dict(scope))
if __name__=='__main__':verify()
