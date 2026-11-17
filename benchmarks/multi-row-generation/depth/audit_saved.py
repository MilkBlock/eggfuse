"""Independent CPU-only replay, including model-hash and readout binding checks."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from contracts import audit
from task import KEYS,VALUES


def tensor(path,name):
    with path.open('rb') as f:
        size=struct.unpack('<Q',f.read(8))[0];header=json.loads(f.read(size));info=header[name]
        if info['dtype']!='F32':raise ValueError('auditor supports F32 checkpoints only')
        begin,end=info['data_offsets'];f.seek(8+size+begin)
        return np.frombuffer(f.read(end-begin),dtype='<f4').reshape(info['shape'])


def main():
    p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path);a=p.parse_args();base=a.checkpoint.parent
    report=json.loads((base/'result.json').read_text());model=base/'model.safetensors'
    assert hashlib.sha256(model.read_bytes()).hexdigest()==report['model_sha256']
    typed=report['protocol'].get('representation')=='typed'
    with np.load(a.checkpoint,allow_pickle=False) as z:
        if typed:
            width=2*KEYS+2*VALUES;w=np.eye(width,z['latent'].shape[-1],dtype=np.float32);b=np.zeros(width,np.float32)
            np.testing.assert_array_equal(z['semantic_weight'],w);np.testing.assert_array_equal(z['semantic_bias'],b)
        else:
            w=tensor(model,'decoder.weight');b=tensor(model,'decoder.bias')
            wk='semantic_weight' if 'semantic_weight' in z else 'decoder_weight';bk='semantic_bias' if 'semantic_bias' in z else 'decoder_bias'
            np.testing.assert_array_equal(z[wk],w);np.testing.assert_array_equal(z[bk],b)
        length=int(z['coords_a'][:,1].max())+1
        result=audit(z['a'],z['b'],z['coords_a'],z['coords_b'],z['coords_pair'],length,z,w,b,typed)
    assert 'mlx.core' not in sys.modules
    print(json.dumps(result,indent=2))
    sys.exit(0 if result['cumulative_exact_graphs'][-1]==result['graphs'] and result['all_finite'] and result['readout_binding_agrees'] else 1)

if __name__=='__main__':main()
