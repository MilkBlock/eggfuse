"""Exact scalar RHS columns fused with a real Cell layout's floating projection."""
import argparse,collections,hashlib,json,sys,time,subprocess,tempfile
from pathlib import Path
import numpy as np
import mlx.core as mx
from compiler import Affine,Unsupported,checked_reference,LIMIT,I64_MAX,I64_MIN
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cell-fixed-state-gpu'))
import run as cell_projection
from model_projection import fold_plan
from gpu_model import forward
from dataset import canonical


def main():
 p=argparse.ArgumentParser()
 for k in ('corpus','slots','model','oracle','output'):p.add_argument('--'+k,type=Path,required=True)
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if not mx.metal.is_available():raise RuntimeError('Metal required')
 mx.set_default_device(mx.gpu)
 recipe=json.loads(Path(__file__).with_name('rule.json').read_text());rule=recipe['rule'];inputs=[1,2];bound=1<<20
 source_rules=json.loads((Path(__file__).resolve().parents[1]/'cell-multi-entry-ridge/source-rules.json').read_text())
 assert rule['metadata']['name']==next(r['source'] for r in source_rules['rules'] if r['rule']==138)
 # Require the actual simple SubTuple entry and its b>1 guard, not an invented standalone formula.
 assert rule['query'][0]['call']=={'table':'SubTuple'}
 assert rule['query'][0]['args'][1:3]==[{'slot':1},{'slot':2}]
 assert rule['query'][1]['call']['primitive']=='>' and rule['query'][1]['args'][0]=={'slot':2} and rule['query'][1]['args'][1]['literal']==1
 program=Affine(rule,inputs,[bound,bound]);assert program.destinations==[8,9]
 m=dict(np.load(a.model));base=cell_projection
 base.D=int(m['dimension']);base.POOL_OPS=bool(m['pool_ops']);base.OP=m['op'];base.EDGE=m['edge'];base.LITERAL=m['literal']
 corpus=json.loads(a.corpus.read_text());cases={c['id']:c for c in json.loads(a.slots.read_text())['cases']};groups=collections.defaultdict(list)
 for r in corpus['records']:
  found=[(n,f) for n,fs in enumerate(r['entry']) for f,(op,args) in enumerate(fs) if op=='SubTuple']
  if len(found)==1:groups[base.digest(base.structure(r['entry']))].append((r,found[0]))
 # Select sharing by input layout only, not prediction success.
 key,rows=max(sorted(groups.items()),key=lambda item:len(item[1]));entry=rows[0][0]['entry'];sub=rows[0][1]
 plan=fold_plan(base.Plan(entry),m);positions=[plan.reads.index((*sub,p)) for p in (1,2)]
 assert len(plan.metadata)==0 # The current selected model already folds its static metadata.
 joint,bias=program.embed(plan,positions);state_width=len(plan.bias)
 raw=[]
 for r,_ in rows:
  c=cases[r['id']];actual,mapping=canonical(c);assert actual==r['entry'] and c['source_sha256']==r['source_sha256']
  indices={}
  for row in c['rows']:
   n=mapping[row['values'][-1]['eq']]
   fact=[row['table'],[['eq',v['sort'],mapping[v['eq']]] if 'eq' in v else ['literal',v['sort'],v['value']] for v in row['values'][:-1]]]
   f=actual[n].index(fact)
   for fld in row['scalar_fields']:indices[n,f,fld['column']]=fld['buffer_index']
  values=[int(c['scalar_values'][indices[pos]]) for pos in plan.reads]
  assert values==plan.gather(actual).astype(np.int64).tolist();raw.append(values)
 raw=np.array(raw,np.int64);qualified=np.array([program.eligible([int(x[p]) for p in positions]) and x[positions[1]]>1 for x in raw]);raw=raw[qualified]
 if not len(raw):raise ValueError('no eligible matched rows')
 # All layout scalar inputs need finite/in-range basis arithmetic, not only RHS operands.
 assert np.all(np.abs(raw)<=bound)
 gw,gb=mx.array(joint),mx.array(bias);onlyw,onlyb=mx.array(plan.weight),mx.array(plan.bias);predict=forward(m);mx.eval(gw,gb,onlyw,onlyb)
 def features(v):return mx.stack([v/4,(v/4)**2,mx.sin(v),mx.cos(v)-1],axis=-1).reshape(v.shape[0],-1)
 def shared(v):
  result=features(v)@gw+gb
  return predict(result[:,:state_width]),result[:,state_width:]
 shared=mx.compile(shared)
 separate=mx.compile(lambda v:predict(features(v)@onlyw+onlyb))
 # Oracle coverage includes guarded failures, exact bound edges, overflows and f32 cancellation.
 rng=np.random.default_rng(791);tests=[[int(x[positions[0]]),int(x[positions[1]])] for x in raw]
 tests += [[-bound,2],[bound,bound],[0,1],[0,0],[0,-1],[bound+1,2],[I64_MAX,2],[I64_MIN,2],[(1<<24)+1,2]]
 tests += rng.integers(-bound,bound+1,size=(1000,2)).tolist()
 with tempfile.TemporaryDirectory() as td:
  request=Path(td)/'in.json';response=Path(td)/'out.json';request.write_text(json.dumps({'cases':tests}))
  subprocess.run([str(a.oracle.resolve()),str(request),str(response)],check=True,timeout=1.)
  oracle=json.loads(response.read_text())
 successes=[];fallback=0;rejected=0;dispatch=[None]*len(tests);gpu_indices=[]
 for case_index,(pair,expected) in enumerate(zip(tests,oracle)):
  if pair[1]<=1:
   assert not expected['matched'] and expected['result'] is None;rejected+=1;continue
  ref=checked_reference(rule,inputs,pair);assert ref==expected['result']
  if program.eligible(pair):successes.append((pair,ref));gpu_indices.append(case_index)
  else:fallback+=1;dispatch[case_index]=checked_reference(rule,inputs,pair)
 # Same embedded GEMM, including unused floating basis columns, checked exactly.
 edge=np.zeros((len(successes),len(plan.reads)),np.float32)
 for i,(pair,_) in enumerate(successes):edge[i,positions]=pair
 edge_out=features(mx.array(edge))@gw+gb;mx.eval(edge_out)
 np.testing.assert_array_equal(np.array(edge_out)[:,state_width:],np.array([r for _,r in successes],np.float32))
 for i,result in zip(gpu_indices,np.array(edge_out)[:,state_width:].astype(np.int64).tolist()):dispatch[i]=result
 assert dispatch==[o['result'] for o in oracle]
 x=mx.array(raw.astype(np.float32));scores,scalars=shared(x);reference=separate(x);mx.eval(scores,scalars,reference)
 np.testing.assert_allclose(np.array(scores),np.array(reference),atol=.005,rtol=.005)
 assert np.array_equal(np.array(scores).argmax(1),np.array(reference).argmax(1))
 expected=np.array([checked_reference(rule,inputs,[int(v[p]) for p in positions]) for v in raw],np.int64)
 np.testing.assert_array_equal(np.array(scalars).astype(np.int64),expected)
 def measure(fn):
  for _ in range(3):fn()
  samples=[]
  for _ in range(20):
   start=time.perf_counter_ns();fn();samples.append((time.perf_counter_ns()-start)/1e6)
  return float(np.median(samples))
 timing=[]
 for repeat in (1,128,1024):
  integers=np.tile(raw,(repeat,1));host=integers.astype(np.float32);device=mx.array(host);mx.eval(device)
  def joint_numeric():mx.eval(shared(device))
  def baseline_numeric():mx.eval(separate(device))
  def joint_request():
   eligible=np.all((integers>=-bound)&(integers<=bound),axis=1)&(integers[:,positions[1]]>1)
   if not eligible.all():raise ValueError('timed cohort unexpectedly requires fallback')
   pred,out=shared(mx.array(integers.astype(np.float32)));mx.eval(pred,out);return np.array(pred),np.array(out).astype(np.int64)
  def baseline_request():
   # Vectorized exact CPU baseline, not an artificially slow primitive interpreter.
   rhs=np.stack([integers[:,positions[0]]+1,integers[:,positions[1]]-1],axis=1)
   pred=separate(mx.array(integers.astype(np.float32)));mx.eval(pred);return np.array(pred),rhs
  timing.append(dict(rows=len(host),repeat=repeat,gpu_state_and_ridge_ms=measure(baseline_numeric),gpu_joint_ms=measure(joint_numeric),
   cpu_rhs_plus_gpu_ridge_request_ms=measure(baseline_request),joint_request_ms=measure(joint_request),
   cpu_rhs_operations_removed_in_bench=2*len(host)))
 result=dict(scope='Standalone exact f32 scalar + ridge fusion from actual Cell recipe and native slot snapshots; no engine takeover',
  recipe_sha256=recipe['recipe_sha256'],rule_name=rule['metadata']['name'],destinations=program.destinations,proof=program.certificates,
  input_bound=bound,layout=key,available_instances=len(rows),eligible_instances=len(raw),state_width=state_width,
  exact_scalar_outputs_verified=len(successes)*2,oracle_cases=len(tests),cpu_fallback_cases=fallback,guard_rejections=rejected,
  ridge_top1_unchanged=True,backpropagation=False,gpu_data_dependent_control=False,weights_added_bytes=joint.nbytes+bias.nbytes-plan.weight.nbytes-plan.bias.nbytes,
  timings=timing,engine_primitive_executions_removed=0,
  caveats=['input-ready scalar values only; original effect order and commit remain authoritative',
   'joint request includes range/guard checks and f32 packing; native slot extraction and publication excluded',
   'large batches repeat one compatible layout, not observed production occupancy',
   'matrix exactness applies to certified integer columns, not learned scores',
   'division, variable multiplication and unbounded i64 are not certified'],
  hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','slots','model','oracle')})
 (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
