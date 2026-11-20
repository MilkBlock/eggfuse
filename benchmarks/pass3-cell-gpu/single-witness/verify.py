"""Check root-only verification, explicit winning bindings and the complete-source denominator."""
import json
from pathlib import Path

def verify(folder=None):
    root=Path(folder) if folder else Path(__file__).resolve().parent
    read=lambda n:json.loads((root/n).read_bytes())
    observed=read('learned.json');cert=read('certified.json')
    for case,n,total,candidates,selected in [('sum-bits',2677,7265,70366,48529),('dot-product',2899,6704,62558,47313)]:
        for seed in (1703,1709):
            key=f'{case}/{seed}';study=observed[key]
            for arm in ('all','high','balanced','coverage','zero-state','none'):
                m=study[arm];assert m['source_aligned'] and m['rhs']==total and m['neural']+m['exact']==total
                assert m['provenance']['all_unique_ids'] and len(set(m['provenance']['ordinals']))==m['neural']
            assert study['none']['neural']==0 and study['all']['neural']==n and study['only']['exact']==0
            c=cert[key]
            for arm in ('certified','guarded','delta','bucket'):
                r=c[arm];assert r['source_aligned'] and r['rhs']==total and len(r['ms'])==10
                if arm!='bucket':assert r['claimed']==n and r['work'][2]==r['work'][1] and r['work'][6]==0
            v=c['certified'];assert v['work'][:3]==[candidates,selected,selected] and v['guard_credited']==0
            assert v['guard'][0]==candidates-selected and v['independent']==[candidates,selected,n,n]
            assert v['provenance']['ordinals']==c['delta']['provenance']['ordinals']
    print('Verified single-witness cohort, CPU score cutoff, marked winning tokens, source alignment and delta control.')

if __name__=='__main__':verify()
