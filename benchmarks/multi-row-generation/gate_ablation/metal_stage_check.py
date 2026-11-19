"""Audit custom Metal row execution against the Figure 05 supervised actor on fresh source panels."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import torch

from gate_data import INPUTS, fresh_panel, templates
from gate_model import GateSystem
from encoder import EClassSchema
from metal_stage import metal_library


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hard_errors(expected, actual):
    errors={}
    for i,(e,a) in enumerate(zip(expected[0],actual[0]),1):
        for key in ('active','pointers','rows'):
            errors[f'run{i}_{key}']=int((e[key]!=a[key]).sum())
    return errors


def compare_hard_and_float(expected, actual, bitwise):
    hard=hard_errors(expected,actual)
    if any(hard.values()):
        raise AssertionError(f'discrete outputs differ: {hard}')
    maximum={}
    for i,(e,a) in enumerate(zip(expected[0],actual[0]),1):
        for key in ('hidden','active_logits','left_logits','right_logits'):
            diff=(e[key]-a[key]).abs();maximum[f'run{i}_{key}']=float(diff.max())
            if bitwise:torch.testing.assert_close(a[key],e[key],rtol=0,atol=0)
    for name,x,y in [('pair_token',expected[1],actual[1]),('relation',expected[2],actual[2])]:
        maximum[name]=float((x-y).abs().max())
        if bitwise:torch.testing.assert_close(y,x,rtol=0,atol=0)
    if not all(torch.isfinite(torch.tensor(list(maximum.values())))):
        raise AssertionError('nonfinite comparison')
    return maximum


def update_max(target, other):
    for k,v in other.items():target[k]=max(target.get(k,0),v)


def main():
    p=argparse.ArgumentParser();p.add_argument('actor_root',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    if not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0':
        raise RuntimeError('MPS without fallback required')
    ts=templates();held=[x for x in ts if x['split']=='heldout'];schema=EClassSchema([x for x in ts if x['split']=='train'])
    dev=torch.device('mps');results={};hashes={}
    for seed in (1703,1709):
        path=args.actor_root/f'supervised-{seed}'/'final.pt';hashes[str(seed)]=digest(path)
        m=GateSystem(schema,seed).load_actor(torch.load(path,map_location='cpu',weights_only=True)).to(dev).eval()
        with torch.inference_mode():
            for t in held:
                table=m.encoder.frozen_bank(schema.bank(t,'pairwise',dev));d=fresh_panel(t);n=len(d['a'])
                maxima={};open_rows=[0,0];closed_rows=[0,0]
                for lo in range(0,n,32):
                    inp=tuple(torch.as_tensor(d[k][lo:lo+32], device=dev,dtype=torch.int32) for k in INPUTS)
                    ref=m.actor(*inp,table,rows=2);dense=m(*inp,table,mode='all',backend='metal_dense');skip=m(*inp,table,mode='all',backend='metal_skip')
                    update_max(maxima,compare_hard_and_float(ref,dense,False));compare_hard_and_float(dense,skip,True)
                    graphs=len(inp[0]);bits=torch.arange(lo*16,(lo+graphs)*16,device=dev).reshape(graphs,2,2,4)%5<3
                    dense=m(*inp,table,backend='metal_dense',gate_override=bits,audit=True)
                    skip=m(*inp,table,backend='metal_skip',gate_override=bits,audit=True)
                    compare_hard_and_float(dense,skip,True)
                    for run in (0,1):
                        mask=bits[:,run].flatten(1,2);s=skip[0][run];ds=dense[0][run]
                        torch.testing.assert_close(s['executed'],mask.int());torch.testing.assert_close(ds['executed'],torch.ones_like(ds['executed']))
                        if not (ds['work_checksum'][~mask]>0).all() or not (s['work_checksum'][~mask]==0).all():
                            raise AssertionError('wrong physical or dense body evidence')
                        open_rows[run]+=int(mask.sum());closed_rows[run]+=int((~mask).sum())
                results[f'{seed}/{t["id"]}']=dict(graphs=n,open_original_hard_exact=True,mixed_dense_and_skip_exact=True,
                    open_parent_max_abs=maxima,masked_open_rows_per_run=open_rows,masked_skipped_rows_per_run=closed_rows)
    report=dict(torch=torch.__version__,device='mps',grid='one 32-thread SIMD group per graph/lane per round',
                simd_width=metal_library().score_physical.thread_execution_width,actor_sha256=hashes,results=results,
                shader_source_sha256=digest(Path(__file__).with_name('metal_stage.py')),
                counters='audit shader only; timed dense and timed physical have no instrumentation')
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(seed_panels=len(results),graphs=sum(x['graphs'] for x in results.values()),
                          max_pair_token_error=max(x['open_parent_max_abs']['pair_token'] for x in results.values()))))


if __name__=='__main__':main()
