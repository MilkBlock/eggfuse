"""Audit identical model inputs with contradictory Eq labels; no training or mutation."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np,mlx.core as mx
from neural_ordered_relations import ordered_model
from train_neural_cell_chains import incoming_tokens
from collections import defaultdict
parser=argparse.ArgumentParser();parser.add_argument('weights',type=Path);parser.add_argument('output',type=Path);parser.add_argument('datasets',nargs='+',type=Path);args=parser.parse_args()
paths=args.datasets
groups=defaultdict(list)
for path in paths:
 d=dict(np.load(path));m=ordered_model(d['p_x'].shape[-1],d['relations'].shape[-1],True);m.load_weights(str(args.weights))
 for start in range(0,len(d['valid']),128):
  b={k:mx.array(v[start:start+128]) for k,v in d.items()};p={k[2:]:v for k,v in b.items() if k.startswith('p_')};c={k[2:]:v for k,v in b.items() if k.startswith('c_')}
  _,first=m(p['x'],p['edges'],p['mask'],p['request'],p['relations']);_,second=m.transition(incoming_tokens(m,c,first),c['edges'],c['mask'],c['request'],c['relations'])
  incoming=mx.where((b['source_kind']==1)[...,None],first[:,None,:],m.encode(b['seed_x']));incoming=mx.where((b['source_kind']==2)[...,None],second[:,None,:],incoming)+b['source_tags'];mx.eval(incoming)
  features=[np.array(incoming)]+[np.array(b[k]) for k in ('edges','mask','request','relations')]
  for j in range(len(features[0])):
   i=start+j
   if not d['valid'][i]:continue
   h=hashlib.sha256(b''.join(v[j].tobytes() for v in features)).hexdigest();label=(np.packbits(d['eq_mask'][i]).tobytes()+np.packbits(d['eq_target'][i].astype(bool)&d['eq_mask'][i]).tobytes()).hex()
   groups[h].append(dict(dataset=path.name,index=i,case=int(d['case'][i]),rule=int(d['rule'][i]),label=label))
conflicts=[v for v in groups.values() if len({x['label'] for x in v})>1]
r=dict(scope='Exact floating transition input collisions across synthetic train/test positives',positive_states=sum(map(len,groups.values())),unique_inputs=len(groups),conflicting_groups=len(conflicts),conflicts=conflicts)
r['weights_sha256']=hashlib.sha256(args.weights.read_bytes()).hexdigest();r['dataset_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
args.output.write_text(json.dumps(r,indent=2)+'\n');print({k:v for k,v in r.items() if k!='conflicts'})
