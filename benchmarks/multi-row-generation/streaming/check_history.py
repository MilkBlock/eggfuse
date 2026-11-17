"""Audit paired initialization and causal intervention boundaries from artifacts."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();records={};hashes=None
    for seed in (1703,1709):
        initial=[]
        for arm in ('feedback','blind'):
            path=a.root/f'{arm}-{seed}';meta=json.loads((path/'result.json').read_text());sha=hashlib.sha256((path/'initial.safetensors').read_bytes()).hexdigest()
            assert sha==meta['protocol']['initial_model_sha256'];initial.append(sha)
            if hashes is None:hashes=meta['protocol']['final_input_hashes']
            else:assert hashes==meta['protocol']['final_input_hashes']
        assert initial[0]==initial[1];records[f'initial-{seed}']=initial[0]
        path=a.root/f'feedback-{seed}'
        for panel in ('iid','triple_right','four_right'):
            for rows,length in ((4,2),(2,4)):
                base=f'{panel}-{rows}x{length}'
                with np.load(path/f'{base}.npz') as full:
                    for intervention in ('erase','local'):
                        with np.load(path/f'{base}-{intervention}.npz') as changed:
                            for key in ('latent','token','active_logits','pointer_logits','field_logits','active','pointers','fields','addresses'):
                                np.testing.assert_array_equal(full[key][:,::length],changed[key][:,::length])
                            later=[i for i in range(8) if i%length]
                            assert np.any(full['token'][:,later]!=changed['token'][:,later])
                            records[base+f'-{seed}-{intervention}']=dict(first_round_identical=True,later_token_changed=True)
    print(json.dumps(dict(status='pass',checks=records,shared_fresh_input_hashes=hashes),indent=2))

if __name__=='__main__':main()
