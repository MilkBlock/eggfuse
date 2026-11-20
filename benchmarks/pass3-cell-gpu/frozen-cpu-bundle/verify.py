import json
from pathlib import Path


def verify(folder):
    d=json.loads((folder/'relocation.json').read_bytes())
    assert set(d)=={'sum-bits','pair'}
    for name,v in d.items():
        assert v['profile']=='frozen-ports/v1' and 100*v['directly_allocated']>=98*v['all_fresh']
        assert len(v['state'])==len(v['compiled_plan'])==64 and v['sealed']>0 and v['files']==8
    assert d['sum-bits']['rhs']==7265 and d['pair']['rhs']==2 and d['pair']['foreign_image_rejected']
    assert set(d['sum-bits']['corruptions_rejected'])=={'ports.bin','plans.json','request.json','incompatible_settings'}
    assert all(d['sum-bits']['corruptions_rejected'].values())
    return d

def verify_native(folder):
    reports=json.loads((folder/'native-parity.json').read_bytes())
    expected={'sum-bits','dot-product','jacobi-1d','conjugate-gradient','3mm','deriche','pair'}
    audited={'sum-bits','pair'}
    assert set(reports)=={f'{case}/1703' for case in expected}|{f'{case}/1709' for case in audited}
    cpu={}
    for filename in ('anchors.json','transfer.json'):
        cpu.update(json.loads((folder.parent/'pair-source-frontier'/filename).read_bytes()))
    relocation=verify(folder)
    manifest=json.loads((folder.parent/'prefix-transfer/manifest.json').read_bytes())
    for key,row in reports.items():
        case,seed=key.split('/')
        assert row['rules']>=row['active_plans']>0
        assert row['native_compile_ms']>0 and row['python_reference_ms']>0
        assert row['profile_execution']['views']==2 and row['profile_execution']['sealed_before_verifier']
        assert row['profile_execution']['single_policy']==row['profile_execution']['multi_policy']=='learned'
        assert row['profile_execution']['sealed_tuples']>0
        assert row['table_sha256']==reports['sum-bits/'+seed]['table_sha256']
        if case in audited:
            assert row['per_run_aligned'] and row['plan_sha256']==relocation[case]['compiled_plan']
            for name,existing in [('source_rhs','rhs'),('runs','runs'),('state','state')]:
                assert row[name]==relocation[case][existing]
        else:
            assert 'per_run_aligned' not in row
        if case!='pair':
            assert row['source_rhs']==cpu[case]['vanilla']['rhs'] and row['runs']==cpu[case]['vanilla']['runs']
            assert row['state']==cpu[case]['off']['state_sha']
        if case in manifest:
            assert row['program_sha256']==manifest[case]['program']
            assert row['plan_sha256']==manifest[case]['plans']
    assert reports['pair/1703']['errors_preserve_destination']
    assert reports['pair/1709']['table_sha256']!=reports['pair/1703']['table_sha256']
    return reports


if __name__=='__main__':
    folder=Path(__file__).resolve().parent
    print('Verified',len(verify_native(folder)),'source-only bundle compilations and both relocated runtime checks')
