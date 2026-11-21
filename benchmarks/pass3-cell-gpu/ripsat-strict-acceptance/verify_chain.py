"""Reconcile authenticated source origins, genuine local histories, and observed publication uses."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(f):return json.loads((HERE/f).read_bytes())
def check():
    catalog=read('catalog-chains.json');rows=read('chain-audit.json');pins=read('companion-pins.json');trust=read('../ripsat-donor-evidence/trust.json')
    assert catalog['strict_paths']==[[[143,1,55]]] and catalog['static_only_paths']==[[[446,0,446]]]
    assert catalog['strict_certificates']==2 and catalog['production_join']['genuine_two_step_paths']==0
    assert catalog['production_join']['synthetic_positive_paths']==1 and len(catalog['production_join']['rejected_controls'])==10
    for s in catalog['catalog_counts'].values():assert s['same_middle_and_input_ref']<=s['same_middle_occurrence']<=s['same_donor_schema_adjacent']<=s['schema_adjacent']
    for donor,leaf,root,middle,terminal,n_all,n_143 in [('dot-product',44,1737,1822,[2625],257,36),('jacobi-1d',192,5314,5598,[],1347,153)]:
        q=rows[donor];p=pins[donor];raw=read(p['file']);first=raw['first_origin_sample'];n=q['nominated_middle']
        assert hashlib.sha256((HERE/p['file']).read_bytes()).hexdigest()==p['sha256']
        assert raw['source_origin_sha256']==trust['samples'][p['source_sample']]['origin_sha256']
        assert raw['native_acceptance_sha256']==trust['samples'][p['source_sample']]['acceptance_sha256']
        assert raw['reference']['state_sha']==q['state_sha'] and raw['reference']['root_commits_sha']==q['root_commits_sha']
        assert len(catalog['local_replay_triples'][donor]['triples'])==1
        assert catalog['local_replay_triples'][donor]['triples'][0]['local_records']==[0,8,12]
        assert q['signed_first_steps']==leaf and q['signed_second_steps']==0
        assert q['by_operation']['0:let:Single']['static_alias_elided']==leaf
        assert q['by_operation']['1:set:Get']['fresh']==leaf
        assert q['by_operation']['1:set:Get']['later_external_named_uses']==n_all
        assert sum(x[-1] for x in q['outgoing_uses'] if x[1]==143)==n_143
        assert n['producer_serial']==root and n['consumer_serial']==middle and n['middle_signed'] and n['elided_single_at_op0']
        [port]=n['get_at_op1'];assert port['kind']=='fresh' and port['op']==1 and p['fact']==port['fact']==(port['cell']<<32)|1
        assert [k['serial'] for k in port['later_143']]==raw['later_143_paid_serials']==terminal
        assert not raw['later_143_internal_serials'];assert all(c['external'] for c in port['later_143'])
        assert len(raw['companions'])==len(terminal)
        for item,tail in zip(raw['companions'],terminal):
            assert item['producer']==first['consumer'] and item['consumer']['serial']==tail
            assert item['birth_event'][4]==raw['middle_set_fact']==port['fact']
            assert item['birth_event'][5][1]==55 and item['producer']['epoch']==item['original_version']==port['version']
            named=item['consumer']['rows'][0]['named'];assert named=={'atom':0,'row':{'Fact':{'cell':port['cell'],'op':1}},'version':port['version']}
            assert item['consumer']['epoch']>item['producer']['epoch']
    print('Both authenticated donor middle occurrences, local two-edge reports, all signed root returns and 10 production join guards verified.')
if __name__=='__main__':check()
