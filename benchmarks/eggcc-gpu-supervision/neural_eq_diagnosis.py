"""CPU-only explanation of invalid neural Eq states; never feeds GPU inputs."""
import numpy as np


def diagnose(scores, truth, mask, local_truth, width):
    scores=np.asarray(scores);truth=np.asarray(truth,bool);mask=np.asarray(mask,bool)
    local=np.asarray(local_truth,bool);a,b=np.triu_indices(width,1)
    parent=list(range(width))
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    for i,j in zip(a[(scores>=0)&mask],b[(scores>=0)&mask]):
        parent[root(int(i))]=root(int(j))
    closed=np.array([root(int(i))==root(int(j)) for i,j in zip(a,b)])
    wrong=((closed!=truth)|~np.isfinite(scores))&mask
    if not wrong.any():return None
    pairs=[]
    for k in np.flatnonzero(wrong):
        pairs.append(dict(slots=[int(a[k]),int(b[k])],predicted=bool(closed[k]),
                          expected=bool(truth[k]),local_expected=bool(local[k]),
                          raw_score=float(scores[k]) if np.isfinite(scores[k]) else None,
                          external_equality=bool(truth[k] and not local[k])))
    return dict(pairs=pairs,has_false_merge=bool((closed&~truth&mask).any()),
                has_external_missing=bool((~closed&truth&~local&mask).any()))
