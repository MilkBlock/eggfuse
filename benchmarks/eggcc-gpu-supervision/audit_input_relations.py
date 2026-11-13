"""Replay input relations from actual GPU-selected witnesses, never future labels."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from device_input_relations import inputs,encode,projection
from device_match_capture import audit


def restore(archive,prefix):
    out={}
    for key in archive.files:
        if not key.startswith(prefix):continue
        parts=key[len(prefix):].split('/');node=out
        for part in parts[:-1]:node=node.setdefault(part,{})
        node[parts[-1]]=archive[key]
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    meta=json.loads(a.capture.with_suffix('.json').read_text());digest=hashlib.sha256(a.capture.read_bytes()).hexdigest()
    if digest!=meta['capture']['artifact_sha256'] or not meta['capture']['passed']:raise ValueError('unverified capture')
    weight=projection();reports=[]
    with np.load(a.capture) as archive:
        prefixes=sorted(k[:-len('rule')] for k in archive.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k)
        for prefix in prefixes:
            c=restore(archive,prefix)
            if not bool(c['recorded']):continue
            proof=audit(meta['recipe'],c)
            if not proof['passed']:raise ValueError(proof)
            x=inputs(meta['recipe'],c)
            if not len(c['input_ports']):continue
            mask=c['accepted'];started=time.perf_counter();cpu,count=encode(x,weight,np);cpu_time=time.perf_counter()-started
            dx={k:mx.array(v) for k,v in x.items()};dw=mx.array(weight);mx.eval(dx,dw)
            fn=mx.compile(lambda y:encode(y,dw,mx));gpu,gc=fn(dx);mx.eval(gpu,gc)
            # One warm replay is diagnostic only, not an end-to-end speed benchmark.
            started=time.perf_counter();gpu,gc=fn(dx);mx.eval(gpu,gc);gpu_time=time.perf_counter()-started
            np.testing.assert_allclose(np.array(gpu),cpu,atol=2e-6)
            np.testing.assert_array_equal(np.array(gc),count)
            reports.append(dict(rule=int(c['rule']),accepted=int(mask.sum()),matched=int(c['bindings']['live'].sum()),
                accepted_pairs=count[mask].sum(axis=0).tolist(),accepted_nonzero_features=int(np.count_nonzero(cpu[mask])),
                feature_bytes=int(cpu[mask].nbytes),padded_feature_bytes=cpu.nbytes,input_ports=len(c['input_ports']),
                gpu_cpu_max_abs=float(np.max(abs(np.array(gpu)-cpu))),cpu_feature_seconds=cpu_time,gpu_warm_feature_seconds=gpu_time))
    result=dict(scope='standalone selected-witness feature replay; not full egglog or a trained accuracy result',capture_sha256=digest,
        partition=meta['capture']['partition'],case=meta['capture']['case'],backpropagation=False,installed=False,
        channels=['same logical source and generation','same source port','same typed current Eq root','same typed Eq root across sources'],
        floating_columns=128,projection_bytes=weight.nbytes,blocks=reports,
        limitations=['No fitting or test-set selection','Pair mask costs O(input ports squared); projection uses real source floating tokens',
            'One warm launch excludes upload and compilation; not end-to-end acceleration','Requires broader positive Eq samples before semantic accuracy comparison'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
