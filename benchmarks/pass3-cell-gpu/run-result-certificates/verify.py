import json,sys
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    groups=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    phys=checked(folder,('physical.json',),('conjugate-gradient','3mm'))
    for name,arms in groups.items():
        ref=arms['reference']
        assert set(arms)=={'vanilla','off','reference','rows','classes','tables','two-hit'}
        for k in ('tables','rows','classes','two-hit'):
            s=arms[k]['certificates']
            assert s['writes']>0 and 0<s['peak_entries']<=8192
            assert s['audited']==s['hits']==s['negative_hits']+s['stale_bindings']
            assert s['cross_run_hits']>0 and arms[k]['work'][3]<ref['work'][3]
        assert arms['two-hit']['certificates']['writes']<arms['classes']['certificates']['writes']
    for arms in phys.values():
        for k in ('identity','compressed','eager-compressed'):
            s=arms[k]['certificates']
            assert s['physical_audits']==sum(s['physical_checks'])>0 and s['audited']==s['hits']
        for f in ('hits','writes','stale_bindings','negative_hits'):
            assert arms['identity']['certificates'][f]==arms['compressed']['certificates'][f]==arms['two-hit']['certificates'][f]
    rss=json.loads((folder/'rss.json').read_bytes())
    for case in groups:
        for k,v in rss[case].items():assert len(v['bytes'])==3 and median(v['bytes'])==v['median']>0
    fixture=json.loads((folder/'fixture.json').read_bytes())
    for k,v in fixture.items():
        if k=='projected':continue
        assert all(v[f]==fixture['projected'][f] for f in ('winners','graph','source_runs','write_runs','unions','cells'))
    assert any(fixture['classes']['unions'])
    w=fixture['classes']['certificates']
    assert w['audited']==w['hits']==6 and w['expiry']==1 and w['changed_header']==2
    probe=json.loads((folder/'representation-probe.json').read_bytes())
    assert {x[0] for x in probe['observed']}=={3,4}
    assert probe['field_mismatches_rejected']==probe['epoch_mismatches_rejected']==2
    return groups


if __name__=='__main__':print('Verified repeated-result and direct Cell certificates, actual physical IDs and source ledgers on',len(verify(HERE)),'programs')
