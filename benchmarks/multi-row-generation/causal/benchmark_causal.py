"""Same-input timing against a genuinely trained causal K/V-cache decoder."""
import sys,argparse,json,time,statistics,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
from causal_model import CausalGenerator
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import Generator
from benchmark import inputs
from checked_forward import check
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'typed'))
from typed_model import TypedGenerator
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'depth'))
from contracts import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('output',type=Path);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);root=Path('/Volumes/EggFuseWorkspace/experiments')
    dirs={'block_continuous':root/'multi-row-token-interface-20261118'/f'continuous-{a.seed}',
          'block_typed':root/'multi-row-token-interface-20261118'/f'typed-{a.seed}',
          'causal_serial':root/'multi-row-causal-full-source-20261118'/f'serial-{a.seed}'}
    models={};metadata={}
    for name,path in dirs.items():
        metadata[name]=json.loads((path/'result.json').read_text())
        model=TypedGenerator('independent') if name=='block_typed' else CausalGenerator() if name=='causal_serial' else Generator('independent')
        assert hashlib.sha256((path/'model.safetensors').read_bytes()).hexdigest()==metadata[name]['model_sha256']
        model.load_weights(str(path/'model.safetensors'));mx.eval(model.parameters());models[name]=model
    results={}
    for panel in ('two_tails','cycle_tail'):
        with np.load(dirs['block_typed']/f'{panel}.npz') as z:
            aa=z['a'][:32];bb=z['b'][:32];pa,pb,pp=[mx.array(z[k]) for k in ('coords_a','coords_b','coords_pair')]
        length=int(np.max(np.array(pa)[:,1]))+1;rows=int(np.max(np.array(pa)[:,0]))+1
        functions={};weights={}
        for name,m in models.items():
            w,b=m.semantic_readout() if name=='block_typed' else (m.decoder.weight,m.decoder.bias);weights[name]=(w,b)
            def f(x,y,ia,ib,m=m,w=w,b=b,name=name):
                out=m.forward_grouped(x,y,pa,pb,length,rows,2,'serial') if name=='causal_serial' else m.forward(x,y,pa,pb,pp)
                verdict=check(ia,ib,out,pb,pp,w,b)
                if name=='block_typed':
                    symbols=out['latent'][...,:40];padding=out['latent'][...,40:]
                    fmt=mx.all((symbols==0)|(symbols==1),axis=(2,3))&mx.all(padding==0,axis=(2,3))
                    offset=0
                    for width in (16,16,4,4):
                        fmt &= mx.all(mx.sum(symbols[...,offset:offset+width],axis=-1)==1,axis=-1);offset+=width
                    verdict['whole_graph'] &= mx.all(fmt,axis=0)
                finite=mx.all(mx.isfinite(out['latent']),axis=(2,3))&mx.all(mx.isfinite(out['field_logits']),axis=(2,3))&mx.all(mx.isfinite(out['pointer_logits']),axis=(2,3))
                verdict['whole_graph'] &= mx.all(finite,axis=0)
                return out,verdict
            functions[name]=mx.compile(f)
        resident=[inputs(aa[i:i+1],bb[i:i+1]) for i in range(32)];mx.eval(resident)
        for f in functions.values():
            for i in range(4):mx.eval(f(*resident[i]))
        measured={name:[] for name in functions};host_times={name:[] for name in functions};raw={name:[] for name in functions}
        names=list(functions)
        for i in range(32):
            order=names[i%3:]+names[:i%3]
            for name in order:
                start=time.perf_counter();out=functions[name](*resident[i]);mx.eval(out);measured[name].append((time.perf_counter()-start)*1000);raw[name].append(out)
        for i in range(32):
            order=names[i%3:]+names[:i%3]
            for name in order:
                start=time.perf_counter();source=inputs(aa[i:i+1],bb[i:i+1]);out=functions[name](*source);mx.eval(out);host_times[name].append((time.perf_counter()-start)*1000)
        # CPU audits cannot alter any inference or timed decision above.
        scores={}
        for name in names:
            w,b=weights[name];mx.eval(w,b);verdicts=[]
            for i,(out,gpu) in enumerate(raw[name]):
                record={k:np.array(v) for k,v in out.items()}
                cpu=audit(aa[i:i+1],bb[i:i+1],np.array(pa),np.array(pb),np.array(pp),length,record,np.array(w),np.array(b),name=='block_typed')
                good=cpu['cumulative_exact_graphs'][-1]==1
                assert good==bool(np.array(gpu['whole_graph'])[0]);verdicts.append(good)
            scores[name]=dict(complete_graphs=sum(verdicts),graphs=32,resident_median_ms=statistics.median(measured[name]),host_median_ms=statistics.median(host_times[name]),
                resident_samples_ms=measured[name],host_samples_ms=host_times[name],
                host_complete_graphs_per_second=sum(verdicts)/(sum(host_times[name])/1000),tokens_per_graph=2*rows*length)
        results[panel]=dict(rows=rows,length=length,lanes=scores,serial_over_typed=scores['causal_serial']['host_median_ms']/scores['block_typed']['host_median_ms'],
            serial_over_continuous=scores['causal_serial']['host_median_ms']/scores['block_continuous']['host_median_ms'])
        print(panel,{name:(s['host_median_ms'],s['complete_graphs']) for name,s in scores.items()},flush=True)
    r=dict(seed=a.seed,results=results,model_sha256={name:r['model_sha256'] for name,r in metadata.items()},
        scope='two-round conditional task, same graphs; feature upload, generation and device verification timed',
        baseline='trained causal decoder using all known source states plus actual emitted-prefix K/V; known-source and external K/V cached',
        limits=['fixed output anchors and finite key vocabulary','different disclosed training data/initialization; not an architecture-only ablation','not eggcc or a free-text language-model baseline','12-round correctness is measured separately'],
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.output.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':main()
