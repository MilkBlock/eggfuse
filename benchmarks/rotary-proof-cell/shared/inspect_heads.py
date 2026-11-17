"""Audit learned primitive heads after fitting; never supplies runtime answers."""
import argparse,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from shared_net import SharedNet
from local_supervision import FEATURES,RELATION_LABEL,SWAP_LABEL,INSERT_LABEL
p=argparse.ArgumentParser();p.add_argument('weights',type=Path);a=p.parse_args()
if not mx.metal.is_available():raise RuntimeError('Metal required')
mx.set_default_device(mx.gpu);m=SharedNet();m.load_weights(str(a.weights))
rel=m.relation(mx.array(FEATURES))[:,0];sw=m.pointer_matrix(mx.arange(7));ins=m.pointer_matrix(mx.zeros((1,),mx.int32),True)
act=m.activation(mx.array([[0.],[1.]]))[:,0];mx.eval(rel,sw,ins,act)
# Only now compare the GPU-generated scores to offline primitive labels.
r=np.array(rel);target=RELATION_LABEL.astype(bool)
result=dict(relation_truth_table_correct=int(np.sum((r>0)==target)),relation_truth_table_cases=256,
            relation_min_signed_margin=float(np.min(np.where(target,r,-r))),
            swap_rows_correct=int(np.sum(np.array(sw).argmax(-1)==SWAP_LABEL)),swap_rows=56,
            insertion_rows_correct=int(np.sum(np.array(ins).argmax(-1)==INSERT_LABEL)),insertion_rows=8,
            activation_correct=bool(np.array_equal(np.array(act)>0,[False,True])),
            limitation='binary primitive inputs only; not a proof for all soft recurrent states')
print(json.dumps(result,indent=2))
