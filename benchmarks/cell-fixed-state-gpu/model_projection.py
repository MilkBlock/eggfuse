"""Fold learned affine state projection into shared layout coefficients offline."""
import numpy as np


def fold_plan(plan,model):
    if 'state_projection' not in model:return plan
    matrix=np.asarray(model['state_projection'],dtype=np.float32);offset=np.asarray(model['state_bias'],dtype=np.float32)
    width=len(plan.bias)+len(plan.metadata)
    if matrix.ndim!=2 or matrix.shape[0]!=width or offset.shape!=(matrix.shape[1],):raise ValueError('state projection shape mismatch')
    if not np.isfinite(matrix).all() or not np.isfinite(offset).all():raise ValueError('nonfinite state projection')
    dynamic=len(plan.bias)
    plan.weight=plan.weight@matrix[:dynamic]
    plan.bias=np.concatenate([plan.bias,plan.metadata])@matrix+offset
    plan.metadata=np.empty(0,np.float32)
    return plan


def reference_state(raw,model):
    if 'state_projection' not in model:return raw
    return raw@model['state_projection']+model['state_bias']
