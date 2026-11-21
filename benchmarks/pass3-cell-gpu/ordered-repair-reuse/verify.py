from pathlib import Path
import json
import hashlib
import sys
from statistics import median

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked

MODES={'off':0,'reverse':1,'payload':2,'key':4,'all':7,'rebase':8,'defer':16,'combined':23,'delayed':32,'delayed-combined':53}


def validate(group):
    for name,arms in group.items():
        base=arms['off']['repair_work']
        fields=('repaired_dependencies','repair_key_hash_changes','repair_collisions')
        for arm,v in arms.items():
            if arm=='vanilla':continue
            report=v['repair_work'];w=report['work'];mode=MODES[arm];assert mode==w['mode']
            assert len(v['ms'])==len(v['phases'])==4
            for phase,t in v['median_phases'].items():
                assert median(r[phase] for r in v['phases'])==t and t>0
            assert all(report[key]==base[key] for key in fields)
            for key in ('live_reverse_edges','peak_reverse_edges','union_wake_visits','union_redirected_edges','reverse_edges_coalesced','repair_key_probes','repair_candidate_checks'):
                assert report['native']['stats'][key]==base['native']['stats'][key],(name,arm,key)
            assert w['unions']==base['work']['unions']>0
            if mode&1:
                assert w['reverse_audits']==w['unions'] and w['merge_insertions']<w['survivor_edges']
            if mode&2:
                assert w['payload_audits']==w['fact_payloads']+w['function_payloads']>0 and w['substitutions']>0
            if mode&4:
                assert w['retired_index_once']==w['retirement_row_reads_saved']==w['index_audits']
                assert w['fact_kept_index']+w['function_kept_index']+w['retired_index_once']>0
            if mode&24:
                assert report['verified_reverse_edges']==report['native']['stats']['live_reverse_edges']>0
                assert w['audited_adoptions']==w['fact_adoptions']+w['function_adoptions']>0
                assert report['native']['stats']['subscription_calls']+w['audited_adoptions']==base['native']['stats']['subscription_calls']
            if mode&32:
                assert 0<w['pending_consumed']==w['payload_audits']<=w['pending_saved']
                assert w['peak_pending']<=32768
    return group


def verify(folder):
    manifest=json.loads((folder/'build-manifest.json').read_bytes())
    assert manifest['source_revision']=='31bf7e41' and manifest['extensions'][-1]==folder.name
    for k,h in manifest['source_sha256'].items():
        assert hashlib.sha256((folder/k.split('/')[-1]).read_bytes()).hexdigest()==h
    basic=validate(checked(folder,('effects.json',),('sum-bits','3mm')))
    subs=validate(checked(folder,('subscriptions.json',),('conjugate-gradient','3mm')))
    late=validate(checked(folder,('late.json',),('3mm','deriche')))
    fixture=json.loads((folder/'fixture.json').read_bytes());gold=fixture['off']
    for v in fixture.values():
        assert v['source']==gold['source'] and v['unions']==gold['unions']
        assert v['size']==[[[None,{'Int':3}]],[],[[{'Int':3},{'Int':1}]],[],[],[]]
    w=fixture['all']['repair']['work']
    assert w['unsupported_schemas']>0 and w['substitutions']>0 and w['retirement_row_reads_saved']>0
    production=json.loads((folder/'production.json').read_bytes())
    assert set(production)=={*basic,*subs,*late}
    expected={}
    for group in (basic,subs,late):
        for case,arms in group.items():
            for arm,r in arms.items():expected[case,arm]=r
    ignore={'audit','audited_adoptions','reverse_audits','payload_audits','index_audits'}
    for case,arms in production.items():
        for arm,row in arms.items():
            ref=expected[case,arm]
            assert row['rhs']==ref['rhs'] and row['state_sha']==ref['state_sha'] and row['root_allocated']==ref['root_allocated']
            x=row['repair_work']['work'];y=ref['repair_work']['work']
            assert not any(x[k] for k in ignore)
            assert all(x[k]==v for k,v in y.items() if k not in ignore)
            assert row['repair_work']['native']==ref['repair_work']['native']
    return {*basic,*subs,*late}


if __name__=='__main__':print('Verified ordered repair phase ablations, logical and physical ledgers and set/union fixture on',len(verify(HERE)),'complete Pass 3 programs')
