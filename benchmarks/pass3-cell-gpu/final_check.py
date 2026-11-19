"""Close the integration audit using a fresh reproduction and pre-deduplication emissions."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from integrate_report import identity


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root,fresh,out):
    summary=read(out/'integration.json');new_timing=read(fresh/'results/cli.json')
    record={};weights={}
    for seed in (1703,1709):
        weights[str(seed)]=read(root/f'router-{seed}.json')
    for n in ('sum-bits','dot-product'):
        new=read(fresh/f'release-{n}/check.json')
        gold=summary[n]
        assert new['acceptance']=='pass' and new['ordered_exact']==gold['aligned']
        assert sha(fresh/f'export-{n}/state.json')==gold['native_contract']['export_sha256']
        for variant in (f'release-one-{n}',*(f'release-{n}-learned-{s}' for s in (1703,1709))):
            assert read(fresh/variant/'check.json')['acceptance']=='pass'
        emissions={}
        for router in ('parity','1703','1709'):
            folder=root/f'row-proposals-{n}-{router}'
            signature,_=identity(folder)
            assert signature==gold['transcript_sha256']
            with np.load(folder/'output.npz',allow_pickle=False) as z:
                e=z['contributions'];assert len(e)==new['completed']
                raw0,raw1,unique0,unique1,shared,doubles=map(int,e.sum(axis=0))
                assert np.array_equal(e[:,2:5].sum(axis=1),z['runs'][:,1])
                assert raw0+raw1==unique0+unique1+2*shared+doubles
                emissions[router]=dict(raw=[raw0,raw1],exclusive=[unique0,unique1],both_proposed=shared,
                                       duplicate_within_row=doubles,both_exclusive_runs=int(((e[:,2]>0)&(e[:,3]>0)).sum()))
        isolated=read(fresh/'results/isolated.json')[n]
        assert isolated['export_sha256']==gold['native_contract']['export_sha256']
        assert set(isolated['opened'])=={'device.json','device.npz','export-schema.json','ports.pt','address.pt'}
        semantic=read(fresh/('native-gpu-sum' if n=='sum-bits' else 'native-gpu-dot')/'check.json')
        assert semantic['status']=='pass'
        record[n]=dict(emissions=emissions,fresh_acceptance=new['acceptance'],fresh_runs=new['completed'],
                       fresh_source_digests=new['ordered_exact'],fresh_native_status=semantic['status'],
                       fresh_timings=new_timing[n],isolated=isolated)
    (out/'release-check.json').write_text(json.dumps(dict(cases=record,router_training=weights),indent=1)+'\n')
    print('All full Run audits, fresh cold CLI and pre-commit row contributions verified.')


if __name__=='__main__':
    q=argparse.ArgumentParser()
    for k in ('root','fresh','out'):q.add_argument(k,type=Path)
    a=q.parse_args();main(a.root,a.fresh,a.out)
