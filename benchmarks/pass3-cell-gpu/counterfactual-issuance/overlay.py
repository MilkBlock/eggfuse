from pathlib import Path
from runpy import run_path

edit=run_path(str(Path(__file__).resolve().parent.parent/'ripsat-set-receipt/overlay.py'))['edit']


def install(crate):
    actor=crate/'src/issuance_actor.rs'
    edit(actor,'    weights: [f32; 3],','    weights: [f32; 3],\n    force: Option<(u64,bool)>,')
    edit(actor,'let take = u < 1. / (1. + (-logit).exp());','''let sampled = u < 1. / (1. + (-logit).exp());
                let take = match self.config.force {
                    Some((id,target)) if id==serial=>target,
                    _=>sampled
                };''')
