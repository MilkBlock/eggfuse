"""Same float32 compiled-blend equations on NumPy CPU, MLX CPU, Metal GPU."""
import argparse,contextlib,hashlib,io,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from gpu_model import forward

p=argparse.ArgumentParser()
for k in ('model','states','output'):p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--repeats',type=int,default=30);a=p.parse_args()
m=dict(np.load(a.model));states=json.loads(a.states.read_text())
if states['model_sha256']!=hashlib.sha256(a.model.read_bytes()).hexdigest():raise ValueError('model mismatch')
if str(m['kind'])!='quadratic_bilinear':raise ValueError('expected selected compact blend')
if not mx.metal.is_available():raise RuntimeError('Metal required for comparison')
raw=np.array([c['state'] for c in states['cases']],np.float32);width=int(m['low_width'])
def cpu(x):
 u=x[:,-width:];outer=(u[:,:,None]*u[:,None,:]).reshape(len(x),width*width)
 return x@m['linear']+(x@m['first']+m['first_bias'])**2@m['nonlinear']+outer@m['bilinear']+m['bias']
def measure(fn):
 for _ in range(3):fn()
 samples=[]
 for _ in range(a.repeats):
  start=time.perf_counter_ns();fn();samples.append((time.perf_counter_ns()-start)/1e6)
 return dict(median_ms=float(np.median(samples)),p10_ms=float(np.percentile(samples,10)),p90_ms=float(np.percentile(samples,90)))
records=[]
for factor in (1,16,128):
 x=np.tile(raw,(factor,1));reference=cpu(x)
 record=dict(rows=len(x),repeated_examples=factor,numpy_cpu=measure(lambda:cpu(x)))
 # Same implementation/compiler, changing only the device, plus practical NumPy baseline.
 for name,device in [('mlx_cpu',mx.cpu),('metal_gpu',mx.gpu)]:
  mx.set_default_device(device)
  with mx.stream(device):
   fn=forward(m);resident=mx.array(x);mx.eval(resident)
   result=fn(resident);mx.eval(result);actual=np.array(result)
   np.testing.assert_allclose(actual,reference,atol=.005,rtol=.005)
   if not np.array_equal(actual.argmax(1),reference.argmax(1)):raise ValueError('top1 differs')
   def numeric():mx.eval(fn(resident))
   def host_boundary():
    out=fn(mx.array(x));mx.eval(out);return np.array(out)
   record[name]=dict(resident_numeric=measure(numeric),host_input_to_host_scores=measure(host_boundary),max_abs_error=float(abs(actual-reference).max()),top1_equal=True)
 records.append(record)
 print(json.dumps(record),flush=True)
configuration=io.StringIO()
with contextlib.redirect_stdout(configuration):np.show_config()
result=dict(scope='Warm float32 fixed blend; same native-produced states, weights and four matmuls; standalone backend comparison',
 repeats=a.repeats,records=records,numpy_configuration=configuration.getvalue(),mlx_version=mx.__version__,
 caveats=['No Graph.slot extraction, layout compilation, proof checks or publication in timings',
 'host boundary means already-available dense states to returned scores, not live runtime end-to-end',
 'Metal shared memory materialization is not discrete PCIe transfer',
 'larger batches repeat examples for throughput, not new accuracy evidence',
 'CPU BLAS uses library defaults; this is not a controlled single-thread CPU test'],
 hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('model','states')})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
