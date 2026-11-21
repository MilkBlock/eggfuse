"""Recompile both frozen target programs and verify static, native and physical evidence."""
import argparse,json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
compiler=run_path(str(HERE/'compile.py'))
def main(exp):
    evidence=HERE.parent/'ripsat-donor-evidence/evidence.json';small=exp/'compact-holdouts-20261121-v1'
    donors={name:small/(name+'-1703')/'program.json' for name in ('dot-product','jacobi-1d')}
    for case,bundle in [('sum-bits',small),('3mm',exp/'extra-pass3-transfer-v1')]:
        target=bundle/(case+'-1703')/'program.json';v=compiler['compile_library'](evidence,donors,target)
        want=json.loads((HERE/(case+'.json')).read_bytes());assert v==want,case
        assert v['strict_named']=={'depth':1,'library':[[[143,1,55]]]} and compiler['two_step_proofs'](v['certificates'])==[]
        assert {z['donor'] for z in v['certificates']}==set(donors)
        for z in v['certificates']:
            local=z['native'];assert local['native_consumer_reads'] and local['local_proof']
            assert z['static']['producer_op']==1 and z['static']['table']=='Single'
            for read in local['native_consumer_reads']:
                assert read['consumer_index']>read['producer_index'] and read['consumer_record']>read['producer_record']
                assert any(site['token']==read['write_read_token'] for event in local['local_proof'] for site in event['output_sites'])
        assert v['strict_named_static_consumer']=={'depth':1,'library':[[[446,0,446]]]}
        assert all(not z['native']['native_consumer_reads'] for z in v['static_only'])
        different=[z for z in v['independently_corroborated'] if z['donor_join']=='other_producer']
        assert any(compiler['edge'](z)==(24,4,65) and z['local_seed_producer_serial']!=z['corroborating_receipt']['producer_serial'] for z in different)
        print(case,v['target_sha256'],v['library_sha256'],len(v['decisions']),len(v['mapped_decisions']))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('exp',type=Path);main(p.parse_args().exp)
