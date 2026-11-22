"""Bake threshold decisions of a frozen structured join reader over its finite ABI."""
import numpy as np
import torch


class FrozenRead:
    """Four fingerprint components, binary (role, freshness) and strict logit > 0."""
    def __init__(self, model):
        if not model.structured or not 1 <= model.bins <= 256:
            raise ValueError('expected structured reader with byte-sized components')
        self.bins=model.bins
        states=torch.tensor([[r,f] for r in (0.,1.) for f in (0.,1.)])
        with torch.no_grad():
            self.left=(model.left_gate(states).flatten()>0).numpy()
            # In roots(), max and min on probabilities commute with the threshold.
            self.sender=(model.messages(states).sigmoid()>.5).numpy()
            features=torch.tensor([[r,f,rf,h/4] for rf in (0.,1.) for r,f in states.tolist()
                                   for h in range(5)])
            logits=model.second(features).reshape(2,4,5)
            self.pair=(logits>0).numpy()
            self.full_overlap_only=not self.pair[:,:,:4].any()
            self.minimum_pair_margin=float(logits.abs().min())

    def __call__(self, states, codes, follower_codes=None):
        if not len(states):
            return []
        category=2*states[:,0]+states[:,1]
        summary=np.zeros((4,self.bins,2),dtype=np.bool_)
        # Each port contributes to exactly four cells of the original max-reduction.
        # No per-key candidate lists or external addresses are stored here.
        src=self.sender[category]
        for i in range(4):
            np.logical_or.at(summary[i], codes[:,i], src)
        context=1-states[:,1]
        chosen=self.left[category].copy()
        for i in range(4):
            chosen &= summary[i,codes[:,i],context]
        roots=np.flatnonzero(chosen)
        if not roots.size:
            return []
        fresh=states[roots,1]
        follower_codes=codes if follower_codes is None else follower_codes
        if self.full_overlap_only:
            word_size=follower_codes.itemsize*follower_codes.shape[1]
            words=np.ascontiguousarray(follower_codes).view(f"V{word_size}").reshape(-1)
            enabled=self.pair[fresh[:,None],category[None,:],4]
            hits=enabled & (words[roots,None]==words[None,:])
        else:
            overlap=(follower_codes[roots,None,:]==follower_codes[None,:,:]).sum(-1)
            hits=self.pair[fresh[:,None],category[None,:],overlap]
        left,right=np.nonzero(hits)
        return list(zip(roots[left].tolist(),right.tolist()))


def float_read(model,states,codes,follower_codes=None):
    with torch.no_grad():
        s=torch.from_numpy(states).float()[None]
        c=torch.from_numpy(codes).long()[None]
        roots=torch.where(model.roots(s,c)[0]>0)[0]
        if not roots.numel():
            return []
        fc=c if follower_codes is None else torch.from_numpy(follower_codes.astype(np.int64))[None]
        left,right=torch.where(model.followers(s,fc,s[:,roots],fc[:,roots])[0]>0)
        return list(zip(roots[left].tolist(),right.tolist()))
