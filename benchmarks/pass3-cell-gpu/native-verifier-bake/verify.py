from pathlib import Path
import json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    cases=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    layouts=read('shapes.json');m=read('generation.json')
    assert len({s['shape'] for s in layouts})==len(layouts)==67
    assert sum(v['rules'] for v in layouts)==226 and sum(v['rules'] for v in layouts if v['rules']>=2)==191
    assert m['emitted_bytes']>0 and m['bootstrap_bytes']<m['linked_bytes']
    for name,arms in cases.items():
        assert set(arms)=={'vanilla','off','projected','shared','all'}
        full=arms['all']['verifier'];shared=arms['shared']['verifier'];dyn=arms['projected']['verifier']
        assert full['installed_native']==226 and shared['installed_native']==191
        assert 0<shared['native_calls']<full['native_calls']<=full['attempts']
        assert dyn['native_calls']==0
        for f in ('attempts','scalar_ops','point_reads','successes','root_constraints'):
            assert full[f]==dyn[f]==shared[f]
    phases=read('phases.json')
    assert set(phases)=={'conjugate-gradient','3mm'}
    for arms in phases.values():
        assert set(arms)=={'off','projected','all'}
        for rows in arms.values():assert len(rows)==3 and all(0<v['check_and_assemble_ms']<v['inference_ms'] for v in rows)
    fixture=read('transfer-fixture.json')
    assert fixture['all-kernels']['projection']['native_calls']>0
    assert fixture['all-kernels']['projection']['installed_native']<fixture['all-kernels']['projection']['programs']
    for k in ('shared-kernels','all-kernels'):
        for f in ('winners','graph','source_runs','write_runs','unions','cells'):
            assert fixture[k][f]==fixture['projected'][f]
        assert any(t[1:3]==[10,5] for t in fixture[k]['winners'])  # The 14-atom computation also commits.
    return cases

if __name__=='__main__':print('Verified native compiler dispatch, source parity, physical allocations and fallback on',len(verify(HERE)),'Pass 3 programs and one new source')
