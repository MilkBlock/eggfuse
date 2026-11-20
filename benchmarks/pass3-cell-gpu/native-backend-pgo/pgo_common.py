"""Use the complete measured CPU provider and the independent exact CPU oracle."""
from hashlib import sha256
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
GPU = HERE.parent
ROOT = GPU.parents[1]
spec = importlib.util.spec_from_file_location('combined_profile', GPU/'composed-cpu/study.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
source = experiment.base
session = source.base.session
DONORS = ('sum-bits', 'dot-product', 'jacobi-1d')
HOLDOUTS = ('conjugate-gradient', '3mm')
BASE_REV = '1291ac63'


def inputs(args, name):
    program, plans, cfg = source.common.config(args, name)
    return program, plans, experiment.choices(cfg,args)['combined-lazy']


def file_digest(path):
    with path.open('rb') as fp:
        h = sha256()
        for chunk in iter(lambda: fp.read(1 << 20), b''):
            h.update(chunk)
        return h.hexdigest()

ARMS=('vanilla-release','learned-release','vanilla-plain','learned-plain','vanilla-use','learned-use')
PROOFS=('raw','multi','commits','physical','children','cells','single_winners','multi_winners',
        'root_parents','root_ids','nested_ids','state_sha','rhs','fresh','direct_cells')
