"""Real recipe CSE and explicit-export projection, with native arithmetic oracle."""
import argparse,copy,hashlib,json,subprocess,tempfile
from pathlib import Path
import numpy as np
import mlx.core as mx
from compiler import Affine,Unsupported,I64_MAX
p=argparse.ArgumentParser();p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if not mx.metal.is_available():raise RuntimeError('Metal GPU required')
mx.set_default_device(mx.gpu);data=json.loads(Path(__file__).with_name('shared-rules.json').read_text());rng=np.random.default_rng(146499);report=[];bound=1<<20
for rid,exports in [('146',None),('499',[21])]:
 rule=data['rules'][rid];inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query' and s['sort']['kind']=='i64']
 plan=Affine(rule,inputs,[bound]*len(inputs),exports=exports)
 cases=rng.integers(-bound,bound+1,size=(2048,len(inputs))).tolist()
 cases += [[bound]*len(inputs),[-bound]*len(inputs),[0]*len(inputs)]
 outside=[I64_MAX,0] if rid=='146' else [I64_MAX,-I64_MAX,-1]
 cases.append(outside)
 with tempfile.TemporaryDirectory() as d:
  request=Path(d)/'in.json';out=Path(d)/'out.json'
  request.write_text(json.dumps(dict(rule=rule,inputs=inputs,cases=cases)))
  subprocess.run([str(a.oracle.resolve()),str(request),str(out)],check=True,timeout=1.)
  expected=json.loads(out.read_text())
 assert not plan.eligible(outside) and expected[-1] is None
 x=mx.array(np.array(cases[:-1],np.float32));w,b=mx.array(plan.coefficients),mx.array(plan.bias)
 fn=mx.compile(lambda values:values@w+b);got=fn(x);mx.eval(got);got=np.array(got)
 for slot,column in plan.output_columns.items():
  np.testing.assert_array_equal(got[:,column],np.array([row[str(slot)] for row in expected[:-1]],np.float32))
 if rid=='146':assert plan.output_columns[7]==plan.output_columns[8] and len(plan.destinations)==2
 else:
  assert len(plan.destinations)==1 and len(plan.certificates)==3
  # Exporting only the final value must not erase an overflowing intermediate.
  try:Affine(rule,inputs,[(1<<24)]*len(inputs),exports=[21])
  except Unsupported:pass
  else:raise AssertionError('unsafe intermediate erased')
 report.append(dict(rule=int(rid),input_slots=inputs,primitive_instructions=len(plan.all_destinations),exported_slots=plan.exports,
  unique_gpu_columns=len(plan.destinations),output_columns=plan.output_columns,proof=plan.certificates,
  eligible_cases=len(cases)-1,exact_exported_results=(len(cases)-1)*len(plan.exports),overflow_fallback_verified=True,
  coefficients=plan.coefficients.tolist(),bias=plan.bias.tolist(),engine_operations_removed=0))
result=dict(scope='GPU arithmetic checks on real recipe instructions with synthetic bounded inputs; not rule-match traffic or runtime takeover',
 source_program=data['program_sha256'],rules=report,shared_connections='template-level slot-to-column map only, no per-instance alias registry',
 oracle_sha256=hashlib.sha256(a.oracle.read_bytes()).hexdigest())
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
