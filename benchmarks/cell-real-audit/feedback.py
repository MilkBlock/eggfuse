"""Enumerate rule-enable events whose closure changes boundary equality."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/cell-real-state'))
import study

states,facts,targets,train,valid,test=study.dataset()
result={'definition':'actions 15/16 only; source boundary partition differs from saturated target',
        'source_sha256':hashlib.sha256(Path(study.__file__).read_bytes()).hexdigest(),'splits':{}}
for name,mask in [('train',train),('validation',valid),('test',test)]:
    examples=[]
    for i in np.flatnonzero(mask):
        for action in (15,16):
            j=int(targets[i,action])
            if states[i][0][:6]!=states[j][0][:6]:
                examples.append(dict(source=int(i),action=action,target=j,target_is_train=bool(train[j]),
                                     before=states[i],after=states[j]))
    result['splits'][name]={'count':len(examples),'examples':examples}
print(json.dumps(result,indent=2))
