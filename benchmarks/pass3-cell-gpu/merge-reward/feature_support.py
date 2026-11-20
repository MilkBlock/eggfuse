"""Distinguish rare verified labels from differences unobservable to this gate."""
from collections import Counter,defaultdict
import json
import sys
from pathlib import Path


def counts(items):
    grouped=defaultdict(Counter)
    for r in items:
        feature=tuple(r['features']);successful=bool(r['counts'][2])
        grouped[feature][successful]+=1
    both=[c for c in grouped.values() if len(c)>1]
    return dict(offers=len(items),won=sum(c[True] for c in grouped.values()),
                distinct_feature_rows=len(grouped),ambiguous_groups=len(both),
                offers_in_ambiguous_groups=sum(sum(c.values()) for c in both),
                classification_errors_even_if_memorized=sum(min(c.values()) for c in both),
                max_depth=max(r['depth'] for r in items))


if __name__=='__main__':
    src=json.loads(Path(sys.argv[1]).read_bytes())
    data={n:counts(v['charges']) for n,v in src.items()}
    data['pooled']=counts([r for v in src.values() for r in v['charges']])
    Path(sys.argv[2]).write_text(json.dumps(data,indent=1)+'\n')
