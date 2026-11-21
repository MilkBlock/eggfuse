"""Verify source and constructor origins, union marginal effects, and every fresh-process OS crossing."""
from statistics import median
from pathlib import Path
from runpy import run_path
from collections import Counter
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));rss=run_path(str(HERE/'rss.py'));read=study['read'];sha=study['sha']
def verify():
    data=read(HERE/'results.json');obs=read(HERE/'rss.json')
    indep=read(HERE.parent/'ripsat-set-receipt/results.json')
    old=read(HERE.parent/'ripsat-neural-bake/results.json') if (HERE.parent/'ripsat-neural-bake/results.json').is_file() else None
    assert set(data)==set(obs)=={'3mm','sum-bits'}
    for case,v in data.items():
        arms=v['arms'];ref=arms['leaf'];u=arms['union'];cm=v['comparison'];control=arms['union_let_only'];r=arms['ripsat']
        assert v['native_sha256']==read(HERE.parent/'ripsat-set-receipt/manifest.json')['exe']
        assert v['library']['certificate_sha256']==sha(study['AUTH']/(case+'.json')) and v['library']['trace_sha256']==sha(study['TRACE'])
        assert v['library']['let_union']==v['library']['let_trace']+v['library']['let_ripsat']-v['library']['let_shared']
        assert v['library']['typed_set']==read(study['AUTH']/(case+'.json'))['strict_named']['set_publication']['path']
        for name,row in arms.items():
            assert all(row[k]==ref[k] for k in study['FIXED']) and all(row['checks'].values())
            assert row['packets']==sum(row['emitted'])+row['child'] and row['fept']==row['visible']/row['packets']
            assert ref['packets']-row['packets']==row['internal']==sum(row['paths'].values())
            if name in ('union','ripsat'):
                z=row['set_counts']
                assert z['confirmed']==row['set_internal'] and z['published']==z['fresh_activations']
                assert len(row['examples'])==1
                e=row['examples'][0];assert e['root']!=e['middle']!=e['consumer'] and e['path']==v['library']['typed_set']
                assert e['ports'][1]==[*e['fact'],e['version'],e['middle_run']]
            else:assert row['set_internal']==0
        assert r['set_internal']==indep[case]['set']['links'] and r['packets']==indep[case]['set']['packets']
        assert r['terminal_ordinals_sha']==u['terminal_ordinals_sha']
        assert cm['from_trace_packets']==arms['trace']['packets']-u['packets']==cm['gained_vs_trace']-cm['lost_vs_trace']
        assert cm['from_same_union_without_set']==control['packets']-u['packets']==cm['union_let_gains']-cm['union_let_losses']
        assert cm['union_terminal_in_trace']+cm['union_terminal_not_in_trace']==u['set_internal']
        assert cm['union_terminal_in_union_let_only']+cm['union_terminal_not_in_union_let_only']==u['set_internal']
        assert cm['ripsat_terminal_retained']+cm['ripsat_terminal_lost']==r['set_internal']
        assert cm['ripsat_terminal_retained']+cm['union_only_terminal']==u['set_internal']
        if old:
            for name,earlier in [('leaf','leaf'),('trace','trace'),('union_let_only','union')]:
                assert arms[name]['signed_ordinals_sha']==study['digest'](old[case]['arms'][earlier]['covered_ordinals'])
        x=obs[case];assert x['semantic_sha256']==sha(HERE/'results.json') and x['calibration_sha256']==sha(rss['cal_file'])
        assert x['reference_levels_kib']==read(rss['cal_file'])[case]['thresholds_kib']['0.9'] and len(x['order'])==32
        for name in study['METHODS']:
            assert len(arms[name]['ms'])==4 and median(arms[name]['ms'])==arms[name]['median_ms']
            values=x['arms'][name];assert len(values)==4
            for i,o in enumerate(values):
                t=o['trace'];assert len(t)==o['samples']>=5 and t[0]==[0,o['entry_kib']]
                assert max(n for _,n in t)==o['peak_kib'] and all(b[0]>a[0] for a,b in zip(t,t[1:]))
                for k,want in [('abs_crossing',x['reference_levels_kib'][0]),('growth_crossing',t[0][1]+x['reference_levels_kib'][1])]:
                    assert o[k]==rss['crossing'](t,want)
                assert all(o['endpoints'][k]==arms[name][k] for k in o['endpoints'])
                assert {f for j,n,f in x['order'] if i==j and n==name}=={True,False}
            for key in ('abs_crossing','growth_crossing'):
                hits=[o[key][1] for o in values if o[key][0]=='reached']
                assert x['summary'][name][key]['outcomes']==dict(Counter(o[key][0] for o in values))
                assert x['summary'][name][key]['median_us']==(median(hits) if hits else None)
    print('Verified four true Set-ABI arms, same-union Set-withheld control, source and final physical origins, and 64 fresh-process outcomes.')
if __name__=='__main__':verify()
