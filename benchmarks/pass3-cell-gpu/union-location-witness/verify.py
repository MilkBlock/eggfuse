import json,sys
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    data=checked(folder,('results.json',),('conjugate-gradient','3mm'))
    donors=read('donors.json');model=read('model.json')
    assert set(donors)=={'sum-bits','dot-product','jacobi-1d'} and set(model['training_cases'])==set(donors)
    assert model['positive']==sum(y[1] for e in donors.values() for _,y in e['features'])
    assert model['negative']==sum(y[0] for e in donors.values() for _,y in e['features'])
    assert len(model['weights'])==12
    for case,arms in data.items():
        assert set(arms)=={'vanilla','off','static','owner','strict','broad','combined','baked','enumerate'}
        for name,row in arms.items():
            if name in ('vanilla','off'):continue
            w=row['locations'];assert w['true_proposed']+w['false_proposed']==w['proposed_fields']
            assert w['true_proposed']<=w['true_seed_positions']<=w['true_positions']
            assert w['complete_lists']<=w['nonempty_unions']<=w['unions']
            assert w['audits']==w['applied'] and w['direct_notifications']+w['ordinary_notifications']==w['total_readers']
            assert w['weighted_patch_work']<=w['exact_patchable_work']
        for k in ('true_proposed','false_proposed','applied','direct_notifications','complete_lists','weighted_patch_work'):
            assert arms['baked']['locations'][k]==arms['combined']['locations'][k]
        assert arms['baked']['locations']['shared_program_hits']>0
        assert arms['broad']['locations']['true_proposed']>arms['static']['locations']['true_proposed']
    assert data['conjugate-gradient']['off']['stale_position_receipts']>0
    phases=read('phases.json')
    for name,arms in phases.items():
        for rows in arms.values():assert len(rows)==3 and all(min(x.values())>0 for x in rows)
    return data

if __name__=='__main__':print('Verified frozen pre-walk field proposals, coverage and physical/source evidence across',len(verify(HERE)),'held-out programs')
