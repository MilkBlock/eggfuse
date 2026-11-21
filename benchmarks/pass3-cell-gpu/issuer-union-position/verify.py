"""Reconcile all actual union roots and each issuer budget with previous full source evidence."""
import json,hashlib
from statistics import median
from budget import compute
from freeze import freeze
from pathlib import Path
HERE=Path(__file__).resolve().parent


def calc(position):
    t=position['totals'];origins=position['origins']
    fs=position['features'];assert all(len(x)==12 for x,_ in fs)
    total=lambda field:sum(b[field] for _,b in fs)
    assert t['attempts']==sum(v['attempts'] for v in origins.values())
    assert t['effective']==sum(v['effective'] for v in origins.values())
    assert t['readers']==sum(v['reader_visits'] for v in origins.values())
    assert total('offers')==t['issued_sites'] and total('selected')==t['choices']
    reached=total('effective');assert reached<=origins['explicit']['effective']<=t['effective']
    assert t['parent_pair_valid']==t['parent_pair_known']==total('pair_valid')
    assert t['committed_input_pair']==t['committed_pair_valid']
    assert total('both_effective')==t['parent_pair_known']
    assert t['parent_pair_known']+t['parent_single_known']+t['no_parent_known']==reached
    assert total('selected_valid')<=total('displaced_valid')<=reached
    for _,b in fs:
        assert b['effective']<=b['reached']<=b['offers']
        assert sum(b['either_valid'])<=b['effective']
        assert sum(b['either_readers'])<=b['readers']
        assert b['local_pair_valid']<=b['local_pair_known']<=b['effective']
        assert b['selected_valid']<=b['selected']<=b['admissible']
    return dict(attempts=t['attempts'],effective=t['effective'],readers=t['readers'],offers=t['issued_sites'],
                admissible=total('admissible'),selected=t['choices'],reached=reached,explicit=origins['explicit']['effective'],
                complete_parent=t['parent_pair_valid'],complete_extended=total('local_pair_valid'),
                parent_high=total('parent_only_valid'),parent_readers=total('parent_only_readers'),all_side_opportunity=sum(sum(b['either_valid']) for _,b in fs),
                nominated=total('displaced_valid'),correct=total('selected_valid'),
                weighted=total('selected_readers'),explicit_readers=origins['explicit']['reader_visits'])


def verify(folder):
    load=lambda f:json.loads((folder/f).read_bytes())
    train=load('donors.json');tests=load('heldout.json');weights=load('model.json');fixture=load('fixture.json')
    assert set(train)=={'sum-bits','dot-product','jacobi-1d'} and set(tests)=={'conjugate-gradient','3mm'}
    assert all(len(x['weights'])==26 for x in weights.values())
    reference={};gpu=folder.parent
    for filename in ('core.json','large.json'):
        reference.update(json.loads((gpu/'composed-cpu'/filename).read_bytes()))
    for case,v in {**train,**tests}.items():
        ledger=v['ledger'];ref=reference[case]['combined-lazy']
        assert all(ledger['checks'].values()) and all(ledger[k]==ref[k] for k in ledger if k!='checks')
        assert v['runs']==reference[case]['vanilla']['runs'] and v['union_events']>0
        prior=None
        for mode,position in v['arms'].items():
            m=calc(position)
            assert v['union_events']==m['effective'] and v['union_hash']==position['totals']['union_hash']
            sites=position['static_sites'];assert len(sites)==50 and sum(len(ss) for _,_,ss in sites)==52
            if prior is not None:
                for k in ('attempts','effective','readers','offers','admissible','selected','reached','explicit','complete_parent','complete_extended','all_side_opportunity','parent_high'):
                    assert m[k]==prior[k],(case,mode,k)
            prior=m
        assert set(v['arms'])==({'all'} if case in train else {'uniform','static','learned-hits','learned-readers'})
    assert load('thresholds.json')==compute(folder)
    assert load('frozen.json')==freeze(train,weights)
    global_runs=load('global.json')
    for case,v in global_runs.items():
        assert case in tests and v['ledger']==tests[case]['ledger']
        ref=calc(tests[case]['arms']['static'])
        assert set(v['arms'])=={'uniform','local-first','baked-hits','learned-hits','learned-readers'}
        for mode,s in v['arms'].items():
            row=calc(s)
            assert s['totals']['union_hash']==tests[case]['union_hash']
            for field in ('effective','readers','explicit','admissible','all_side_opportunity'):assert row[field]==ref[field]
        uniform=calc(v['arms']['uniform']);learned=calc(v['arms']['learned-hits']);baked=calc(v['arms']['baked-hits'])
        assert baked['selected']<learned['selected']<uniform['selected']
        assert baked['correct']>learned['correct']>uniform['correct'] and baked['weighted']>learned['weighted']>uniform['weighted']
    point=load('point.json')['3mm']
    assert point['ledger']==tests['3mm']['ledger']
    old,new=(point['arms'][k] for k in ('parent-local','one-request'))
    assert old['totals']['union_hash']==new['totals']['union_hash']==point['union_hash']
    assert calc(old)['all_side_opportunity']==calc(tests['3mm']['arms']['static'])['all_side_opportunity']
    q=new['totals'];assert q['point_requests']>=q['point_results']>0 and q['point_rechecks']>=q['point_validated_sides']>0
    sites=dict((tuple(site),v) for site,v in new['point_by_site'])
    for index,field in enumerate(('point_requests','point_results','point_ns','point_key_extra_rows','point_rechecks','point_stale','point_recheck_ns','point_validated_sides')):
        assert sum(x[index] for x in sites.values())==q[field]
    for v in (old,new):
        assert len(v['timed'])==4 and min(x['inference_ms'] for x in v['timed'])>0
    assert sites[(317,2)][7]==1957
    before=dict((tuple(k),v) for k,v in old['sites'])[(317,2)]
    after=dict((tuple(k),v) for k,v in new['sites'])[(317,2)]
    assert before[2]==after[2]==1957 and before[3]==0 and after[3]==1957
    assert before[4]==after[4]==after[6]==8387 and before[6]==0
    sample=dict((tuple(k),v) for k,v in new['site_examples'])[(317,2)]
    w=sample['requested'][0]
    assert sample['ordinal']==225752 and w['id']==sample['displaced'] and w['version']==2886
    manifest=load('build-manifest.json')['point']
    for name,f in [('observer','position.rs'),('overlay','overlay.py')]:
        assert manifest[name]==hashlib.sha256((folder/f).read_bytes()).hexdigest()

    for k,v in fixture.items():
        if k=='native':continue
        for field in fixture['native']:
            if field!='position':assert v[field]==fixture['native'][field]
    assert fixture['cert']['position']['origins']['constructor_collision']['effective']>0
    assert sum(b['selected_valid'] for _,b in fixture['cert']['position']['features'])>0
    assert sum(b['selected_valid'] for _,b in fixture['wrong']['position']['features'])==0
    return {**train,**tests}


if __name__=='__main__':print('Verified pre-walk source provenance and frozen issuer budgets on',len(verify(HERE)),'Pass 3 programs and a multi-union source fixture')
