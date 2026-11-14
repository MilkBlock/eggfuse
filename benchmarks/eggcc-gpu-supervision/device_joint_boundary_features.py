"""Fixed dense joint nonlinearity for original input and boundary messages.

Only the output ridge is fitted. These shared projection weights and biases are
fixed independently of training labels; there is no backpropagation.
"""
import numpy as np


def compile_joint(raw_width,base_width,input_width,hidden=256):
    if not 0<raw_width<base_width<input_width or hidden<1:raise ValueError('joint feature layout')
    rng=np.random.default_rng(20261119)
    weight=rng.normal(0,1/np.sqrt(raw_width+input_width-base_width),
                      (raw_width+input_width-base_width,hidden)).astype(np.float32)
    return dict(raw_width=raw_width,base_width=base_width,input_width=input_width,
                raw_weight=weight[:raw_width],boundary_weight=weight[raw_width:],
                bias=rng.uniform(-1,1,hidden).astype(np.float32))


def encode(features,plan,xp):
    if features.ndim!=2 or features.shape[1]!=plan['input_width']:raise ValueError('joint feature input width')
    return xp.tanh(features[:,1:1+plan['raw_width']]@plan['raw_weight']+
                   features[:,plan['base_width']:]@plan['boundary_weight']+plan['bias'])
