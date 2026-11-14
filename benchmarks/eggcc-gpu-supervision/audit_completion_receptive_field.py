"""Diagnose target sufficiency of the existing typed boundary neighborhoods.

Real captures are diagnosis-only; reduced cases must not become training data.
"""
import argparse,hashlib,time,json,numpy as np
from pathlib import Path
from device_snapshot_import import prepare_family
from lower_constructor_sets import lower
from lower_query_literals import lower as lower_literals
from reference_union_family import Reference
from reference_family_schedule import execute
from label_composed_witnesses import target
from audit_input_relations import restore
from device_boundary_context import compile_context,masks
from audit_device_match_readout import rows_from_labels

def audit(path,trace_path,source_rule=290):
 started=time.perf_counter();result=[]
 p=path;m=json.loads(p.with_suffix('.json').read_text());ordinal=m['snapshot_run'];name=m['capture']['case']
 if not m['capture']['passed'] or hashlib.sha256(p.read_bytes()).hexdigest()!=m['capture']['artifact_sha256']:raise ValueError('unverified labels')
 if hashlib.sha256(trace_path.read_bytes()).hexdigest()!=m['trace_sha256']:raise ValueError('trace checksum')
 d=np.load(p)
 tr=json.loads(trace_path.read_text())
 if dict(tr['recipe'],rules=[tr['recipe']['rules'][j] for j in m['source_rules']])!=m['original_recipe']:raise ValueError('source rules changed')
 original=m['original_recipe'];lowered,_=lower(lower_literals(original));snap=next(b['graph'] for b in tr['boundaries'] if b['ordinal']==ordinal)
 local,state,ids,rows=prepare_family(lowered,snap,list(range(len(original['rules']))),1);seed={i:json.loads(v) for v,i in ids.items()};i=0
 labels=rows_from_labels(m['semantic_recipe'],[m['source_rules'].index(int(r)) for r in d['rules']],d['target_eq_classes'])
 prefixes=sorted([k[:-4] for k in d.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k],key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
 for prefix in prefixes:
  c=restore(d,prefix)
  if not bool(c['recorded']):continue
  first=prefix.split('/')[1]==prefixes[0].split('/')[1];rid=int(c['rule'])
  if not first or m['source_rules'][rid]!=source_rule:i+=int(c['accepted'].sum());continue
  b=c['boundary'];n=len(rows)
  if b['live'][n:].any():raise ValueError('audit requires unmodified seed boundary')
  np.testing.assert_array_equal(b['live'][:n],state['present'][:n]&state['visible'][:n]&state['settled'][:n])
  np.testing.assert_array_equal(b['rule'][:n],state['keys'][:n,0])
  if b['slots'].shape[1]!=state['slots'].shape[1]:raise ValueError('seed layout mismatch')
  np.testing.assert_array_equal(b['slot_valid'][:n],state['slot_valid'][:n])
  for field in ('slots','slot_roots'):
   np.testing.assert_array_equal(b[field][:n][b['slot_valid'][:n]],state[field][:n][state['slot_valid'][:n]])
  plan=compile_context(local,rid,b['slots'].shape[1]);conn,_,safe,valid=masks(b,c['bindings'],plan,np);sort=plan['sorts'][safe]
  for lane in np.flatnonzero(c['accepted']):
   row=labels[i];wanted=row['y'][row['quotient']['representatives']];pred=c['completion_readout']['selected'][lane]>=.5
   attached=conn[lane].any(axis=(0,2));out=dict(case=name,sample=i,lane=int(lane),model_correct=bool(np.array_equal(wanted,pred)),regions=[])
   selected=attached.copy()
   for radius in (1,2):
    if radius==2:
     anchors={(int(root),int(typ)) for root,typ in zip(b['slot_roots'][attached&b['live']].ravel(),sort[attached&b['live']].ravel()) if root>=0 and typ>=0}
     selected=np.array([any((int(root),int(typ)) in anchors for root,typ,yes in zip(rs,ts,vs) if yes) for rs,ts,vs in zip(b['slot_roots'],sort,valid)])
    sub=[r for j,r in enumerate(rows) if selected[j]];ref=Reference(original,sub,ids);execute(ref,m['source_control'])
    _,cls=target(local['rules'][rid],c['bindings']['slots'][lane],{j:ref.root(j) for j in range(len(ids))},ref,seed,b['slots'].shape[1])
    actual=np.array([cls[a]==cls[z] for a,z in row['pairs']])[row['quotient']['representatives']]
    out['regions'].append(dict(radius=radius,seed_facts=len(sub),agrees=bool(np.array_equal(wanted,actual)),missed=int((wanted&~actual).sum()),extra=int((~wanted&actual).sum())))
   if not out['model_correct']:
    kept=list(np.flatnonzero(attached[:n]));protected=set(map(int,c['bindings']['witness_rows'][lane]))
    def agrees(indices):
     try:
      ref=Reference(original,[rows[j] for j in indices],ids);execute(ref,m['source_control'])
      _,cls=target(local['rules'][rid],c['bindings']['slots'][lane],{j:ref.root(j) for j in range(len(ids))},ref,seed,b['slots'].shape[1])
      actual=np.array([cls[a]==cls[z] for a,z in row['pairs']])[row['quotient']['representatives']]
      return bool(np.array_equal(wanted,actual))
     except ValueError:return False
    for j in list(kept):
     if j not in protected and agrees([x for x in kept if x!=j]):kept.remove(j)
    out['reduced']=dict(rows=[rows[j] for j in kept],seed_indices=[int(j) for j in kept],protected_indices=sorted(protected),binding={str(j):seed[int(c['bindings']['slots'][lane,j])] for j,v in enumerate(local['rules'][rid]['slots']) if v['definition']=='query'},target=wanted.astype(int).tolist(),predicted=pred.astype(int).tolist())
   result.append(out);i+=1
 d.close()
 return dict(scope='post-execution seed-boundary receptive-field diagnosis; not training or GPU acceleration',source_rule=source_rule,capture_sha256=m['capture']['artifact_sha256'],trace_sha256=m['trace_sha256'],cpu_audit_seconds=time.perf_counter()-started,records=result,limitations=['Only first captured tick and unmodified seed boundaries','Reduced regions preserve target labels, not necessarily model predictions','Greedy reduction is not a globally minimum explanation','Negative Eq labels are relative to the captured selected-family schedule'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('labels',type=Path);p.add_argument('trace',type=Path);p.add_argument('output',type=Path);p.add_argument('--rule',type=int,default=290);a=p.parse_args()
 r=audit(a.labels,a.trace,a.rule);a.output.write_text(json.dumps(r,indent=2)+'\n')
 bad=[x for x in r['records'] if not x['model_correct']]
 print(json.dumps(dict(instances=len(r['records']),incorrect=len(bad),one_hop_sufficient=sum(x['regions'][0]['agrees'] for x in bad),cpu_audit_seconds=r['cpu_audit_seconds'])))
