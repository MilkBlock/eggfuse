"""Reproduce the split signatures and summarize physical versus semantic variation."""
from collections import Counter
from hashlib import sha256
import json

from crossrun_data import SPLITS, dataset


def manifest():
    output = {}
    for name, (_, seed) in SPLITS.items():
        d = dataset(name)
        counts1 = d['target1'][..., 0].sum(1)
        counts2 = d['target2'][..., 0].sum(1)
        collision_graphs = 0
        for records, count in zip(d['target1'], counts1):
            payloads = set(map(tuple, records[:count, 3:]))
            collision_graphs += len(payloads) < int(count)
        output[name] = dict(seed=seed, graphs=len(counts1),
                            nonempty_run2=int((counts2 > 0).sum()),
                            graphs_with_equal_payload_different_parents=collision_graphs,
                            run1_obligations=int(counts1.sum()), run2_obligations=int(counts2.sum()),
                            run1_cardinalities={str(k):int(v) for k,v in sorted(Counter(counts1).items())},
                            run2_cardinalities={str(k):int(v) for k,v in sorted(Counter(counts2).items())},
                            sha256={k:sha256(v.tobytes()).hexdigest() for k,v in d.items()})
    return output

if __name__ == '__main__':
    print(json.dumps(manifest(), indent=2))
