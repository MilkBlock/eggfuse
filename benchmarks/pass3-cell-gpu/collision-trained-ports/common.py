import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
TRAIN=('affine-twins','clamped-ramp','segmented-prefix','window-laplacian')
TEST=('sum-bits','dot-product','jacobi-1d','conjugate-gradient')


def configured(a,name):
    prog,plan,_,req=base.setup(a,name)
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    req=base.query(req,'all',admission)
    req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2)
    return prog,plan,req
