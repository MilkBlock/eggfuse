"""Check the distinct submitted-RHS / physical-ID contracts and matched full-pass measurements."""
import json
from pathlib import Path

def check(folder):
    def read(name):return json.loads((folder/name).read_text())
    holdouts=read('holdout-manifest.json')
    assert set(holdouts)=={'jacobi-1d','conjugate-gradient'}
    for name,cases,variants in [('encoding-results.json',4,['full','shared_wire','resident']),
                                ('checked-results.json',3,['full','resident','checked_slots']),
                                ('negative.json',1,['full','shared_wire','resident'])]:
        results=read(name)
        assert len(results)==(1 if name=='negative.json' else 2*cases)
        for key,arms in results.items():
            vanilla=arms['vanilla'];base=arms['full']
            for variant in variants:
                v=arms[variant]
                assert v['aligned'] and all(v['checks'].values()) and v['rhs']==v['neural_rhs']==vanilla['rhs']
                assert v['direct_cells']*100>=98*v['fresh'] and len(v['ms'])==2*(1+len(variants))
                for k in ('state_sha','raw','commits','physical','multi','children','cells'):
                    assert v[k]==base[k]
            if 'shared_wire' in arms:assert 0<arms['shared_wire']['wire_bytes']<base['wire_bytes']
            assert arms['resident']['wire_bytes']==0
            if name=='negative.json':
                for v in variants:
                    for control in ('wrong-template','wrong-port'):
                        item=arms[v][control];assert item['aligned'] and item['applied']==0 and item['rejected']>0
    profile=read('profile-jacobi.json')
    for arm in profile.values():assert sum(arm['exclusive_groups'].values())==arm['inference_samples']>50
    print('Checked native vanilla, proof identities, complete source endpoints and physical coverage on both larger holdouts.')

if __name__=='__main__':check(Path(__file__).resolve().parent)
