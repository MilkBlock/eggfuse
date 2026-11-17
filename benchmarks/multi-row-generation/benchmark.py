"""Post-training paired generation + verification timing. No source state repair."""
import argparse,json,time,statistics,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
from task import KEYS,VALUES,audit
from network import Generator
from checked_forward import check


def inputs(a,b):
    batch,n=a.shape[:2]
    xa=np.concatenate((np.eye(KEYS)[a[:,:,0]],np.zeros((batch,n,KEYS)),np.eye(VALUES)[a[:,:,1]],np.broadcast_to([1,0],(batch,n,2))),-1).astype(np.float32)
    xb=np.concatenate((np.eye(KEYS)[b[:,:,0]],np.eye(KEYS)[b[:,:,1]],np.eye(VALUES)[b[:,:,2]],np.broadcast_to([0,1],(batch,n,2))),-1).astype(np.float32)
    return mx.array(xa),mx.array(xb),mx.array(a),mx.array(b)


def main():
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    meta=json.loads((args.artifact/'result.json').read_text());mode=meta['protocol']['mode']
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);model=Generator(mode);model.load_weights(str(args.artifact/'model.safetensors'));mx.eval(model.parameters())
    report={}
    for panel in ('seen','final_fanin_layout','final_fanin_rows'):
        with np.load(args.artifact/f'{panel}.npz') as z:
            a=z['a'][:32];b=z['b'][:32];pa,pb,pp=[mx.array(z[k]) for k in ('coords_a','coords_b','coords_pair')]
        def parallel(x,y,ia,ib):
            out=model.forward(x,y,pa,pb,pp)
            return out,check(ia,ib,out,pb,pp,model.decoder.weight,model.decoder.bias)
        def serial(x,y,ia,ib):
            out=model.serial_same_queries(x,y,pa,pb,pp)
            return out,check(ia,ib,out,pb,pp,model.decoder.weight,model.decoder.bias)
        fns={'parallel':mx.compile(parallel),'serial_cached_queries':mx.compile(serial)}
        device=[inputs(a[i:i+1],b[i:i+1]) for i in range(32)]
        mx.eval(device)
        for fn in fns.values():
            for warm in range(4):mx.eval(fn(*device[warm]))
        times={name:[] for name in fns};results={name:[] for name in fns}
        for i in range(32):
            order=list(fns) if i%2==0 else list(reversed(fns))
            for name in order:
                start=time.perf_counter();out=fns[name](*device[i]);mx.eval(out);times[name].append((time.perf_counter()-start)*1000);results[name].append(out)
        # Initial feature construction/upload is charged in a second paired lane.
        host_times={name:[] for name in fns}
        for i in range(32):
            order=list(fns) if i%2==0 else list(reversed(fns))
            for name in order:
                start=time.perf_counter();prepared=inputs(a[i:i+1],b[i:i+1]);out=fns[name](*prepared);mx.eval(out)
                host_times[name].append((time.perf_counter()-start)*1000)
        # Independent audits only after both timed lanes finish. Build expected
        # joins from source facts now, never feed these targets to a timed call.
        match=[];succ=[]
        for g in range(32):
            bm={int(row[0]):j for j,row in enumerate(b[g])};am={int(row[0]):j for j,row in enumerate(a[g])}
            m=[bm[int(row[0])] for row in a[g]];match.append(m);succ.append([am[int(b[g,j,1])] for j in m])
        data=dict(a=a,b=b,coords_b=np.array(pb),coords_pair=np.array(pp),targets=np.array([match,succ]))
        scores={};decoded={}
        for name in fns:
            pointers=np.concatenate([np.array(o[0]['pointers']) for o in results[name]],axis=1)
            fields=[]
            for out,verdict in results[name]:
                latent=np.array(out['latent']).astype(np.float64)
                logits=latent@np.array(model.decoder.weight).astype(np.float64).T+np.array(model.decoder.bias).astype(np.float64)
                cols=[];offset=0
                for width in (KEYS,KEYS,VALUES,VALUES):cols.append(logits[...,offset:offset+width].argmax(-1));offset+=width
                fields.append(np.stack(cols,-1))
            fields=np.concatenate(fields,axis=1);addresses=np.concatenate([np.array(o[0]['addresses']) for o in results[name]],axis=1)
            cpu=audit(data,pointers,fields,addresses)
            gpu=np.concatenate([np.array(o[1]['whole_graph']) for o in results[name]])
            n=a.shape[1];completed=int(gpu.sum());valid_tokens=int(sum(np.array(o[1]['valid']).sum() for o in results[name]))
            median=statistics.median(times[name]);end=statistics.median(host_times[name])
            cpu_bits=[]
            for g in range(32):
                single=dict(data,a=a[g:g+1],b=b[g:g+1],targets=data['targets'][:,g:g+1])
                verdict=audit(single,pointers[:,g:g+1],fields[:,g:g+1],addresses[:,g:g+1])
                cpu_bits.append(verdict['whole_graph_passed']==1)
            assert np.array_equal(gpu,np.array(cpu_bits)), 'GPU/CPU per-graph verdict mismatch'
            assert completed==cpu['whole_graph_passed']
            scores[name]=dict(graphs=32,whole_graph_passed=completed,cpu_audit=cpu,
                resident_forward_check_median_ms=median,host_features_forward_check_median_ms=end,
                resident_samples_ms=times[name],host_samples_ms=host_times[name],
                valid_tokens_per_second=valid_tokens/(sum(times[name])/1000),
                complete_graphs_per_second=completed/(sum(times[name])/1000),
                host_complete_graphs_per_second=completed/(sum(host_times[name])/1000),tokens_per_complete_graph=2*n)
            decoded[name]=(pointers,fields)
        report[panel]=dict(lanes=scores,decoded_equal=all(np.array_equal(x,y) for x,y in zip(decoded['parallel'],decoded['serial_cached_queries'])),
            host_speed_ratio=scores['serial_cached_queries']['host_features_forward_check_median_ms']/scores['parallel']['host_features_forward_check_median_ms'])
    result=dict(mode=mode,seed=meta['protocol']['seed'],panels=report,
        scope='same-graph neural forward plus readout-bound GPU verification; initial input lane also includes feature construction/upload',
        warning='serial cached-query emission is not a trained autoregressive baseline; fixed output placement and finite relation domain',
        model_sha256=meta['model_sha256'],source_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('benchmark.py','checked_forward.py','network.py')})
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:dict(ratio=v['host_speed_ratio'],equal=v['decoded_equal'],passed=v['lanes']['parallel']['whole_graph_passed'],parallel_ms=v['lanes']['parallel']['host_features_forward_check_median_ms']) for k,v in report.items()}))

if __name__=='__main__':main()
