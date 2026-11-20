"""Independently audit conservation of ordered source evidence and publication work."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/name).read_bytes())


def verify(name):
    data=read(name);contracts=read('contract.json')
    assert set(data)==set(contracts)=={'sum-bits','dot-product','deriche'}
    for case,result in data.items():
        contract=contracts[case];arms=result['arms'];ref=arms['original']
        assert contract['entry_rules']==580 and not contract['native_pending_table_readers']
        assert result['same_build_native_publication']['publication']['row_reads']>0
        dirty=set()
        for label,a in arms.items():
            assert len(a['ms'])==4 and len(a['wall_ms'])==4
            if label=='vanilla':
                assert a['rhs']==ref['proof']['rhs'] and a['graph']==ref['proof']['state_sha']
                continue
            assert a['aligned'] and a['proof']==ref['proof'] and a['fresh']*98<=a['proof']['direct_cells']*100
            assert len(a['phases_ms'])==4
            assert a['publication']==ref['publication'] and a['columns']==ref['columns']
            assert a['entry']['stats']['node_notifications']==ref['entry']['stats']['node_notifications']
            s=a['reader']
            if not s:continue
            assert s['pending_attempts']==s['pending_added']==s['pending_omitted']==0
            dirty.add(s['dirty_transitions'])
            if label in ('entries','combined','masks','clean'):
                assert s['retired_nodes'] and s['removed_node_visits'] and s['spine_kept']
            if label in ('clean','clean-only'):
                assert s['already_dirty']+s['dirty_transitions']==s['unique_wakes']
            if a.get('equality'):
                e=a['equality']
                assert e['empty_records']<=e['row_records'] and e['empty_retired']<=e['empty_records']
        assert len(dirty)==1
        if result['separate_profile']:
            for p in result['separate_profile'].values():
                assert len(p['samples'])==3 and len(p['median_ms'])==8
                assert 0<sum(p['median_ms'][1:])<p['median_ms'][0]
    print('Checked',name,'source schedule, digests, learned roots, unchanged hot indexes and notification bounds.')


if __name__=='__main__':
    verify('readers.json')
    if (HERE/'clean.json').exists():verify('clean.json')
