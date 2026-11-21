import hashlib,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));read=study['read'];sha=study['sha']
m=read(HERE/'manifest.json');links=read(HERE/'links.json');work=read(HERE/'work.json')
for p,h in m['sources'].items():assert sha(HERE.parent/p)==h,p
for case,r in read(HERE/'results.json').items():
    study['check'](r);q=r['set'];base=r['let'];auth=HERE.parent/'ripsat-publication-chain'/(case+'.json');spec=read(auth)['strict_named']['set_publication']
    assert sha(auth)==q['authorization_sha256']==m['authorization'][case]
    assert r['faults']['spoofed_target'] and r['faults']['missing']['counts']['withheld']==q['set_counts']['fresh_activations']
    for n in ('let','set'):
        a=r[n];w=work[case][n]
        assert len(a['ms'])==len(a['wall_ms'])==4 and a['median_ms']==median(a['ms']) and a['median_wall_ms']==median(a['wall_ms'])
        assert w['internal_child_logits']==0 and w['full_bank_without_scores']+w['mixed_prebound_without_scores']==w['internal']
    assert len(links[case])==q['links']==base['packets']-q['packets']
    for x in links[case]:
        assert x['path']==spec['path'] and x['ports'][1][:2]==x['fact'] and x['ports'][1][2]==x['version']
        assert x['ports'][0][3]<x['ports'][1][3]==x['middle_run']<x['consumer_run']
    assert q['terminal_origins']['typed'][1]<=q['terminal_origins']['typed'][0] and q['terminal_origins']['paid']==q['terminal_origins']['dynamic']==[0,0]
    print(case,q['links'],q['terminal_origins']['typed'],base['visible_per_packet'],q['visible_per_packet'])
assert any((x['root'],x['middle'],x['consumer'])==(1737,1822,2625) and x['fact']==[971,1] and x['version']==135 for x in links['dot-product'])
