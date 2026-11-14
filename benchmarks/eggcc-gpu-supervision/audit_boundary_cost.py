"""Bounded boundary-encoder cost audit, not end-to-end runtime speed."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_input_relations import restore
from device_boundary_context import compile_context,encode
from audit_snapshot_queries import device


def bytes_of(x):
    if isinstance(x,dict):return sum(bytes_of(v) for v in x.values())
    return x.nbytes if isinstance(x,np.ndarray) else 0


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    meta=json.loads(a.capture.with_suffix('.json').read_text())
    if not meta['capture']['passed'] or hashlib.sha256(a.capture.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture provenance')
    results=[];seen=set()
    with np.load(a.capture) as f:
        prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix);rid=int(c['rule'])
            if rid in seen or not bool(c['recorded']) or not c['accepted'].any():continue
            seen.add(rid);b=c['boundary'];bindings=c['bindings'];plan=compile_context(meta['recipe'],rid,b['slots'].shape[1])
            started=time.perf_counter();cpu=encode(b,bindings,plan,np);cpu_seconds=time.perf_counter()-started
            started=time.perf_counter();db,di,dp=map(device,(b,bindings,plan));mx.eval(db,di,dp);upload=time.perf_counter()-started
            fn=mx.compile(lambda boundary,inputs:encode(boundary,inputs,dp,mx))
            started=time.perf_counter();gpu=fn(db,di);mx.eval(gpu);first=time.perf_counter()-started
            started=time.perf_counter();gpu=fn(db,di);mx.eval(gpu);warm=time.perf_counter()-started
            started=time.perf_counter();actual=tuple(np.array(x) for x in gpu);readback=time.perf_counter()-started
            np.testing.assert_allclose(actual[0],cpu[0],atol=2e-6);np.testing.assert_array_equal(actual[1],cpu[1])
            results.append(dict(rule=rid,accepted=int(c['accepted'].sum()),padded_lanes=len(bindings['live']),cell_capacity=len(b['live']),slot_width=b['slots'].shape[1],ports=len(plan['ports']),
                feature_columns=cpu[0].shape[1],feature_bytes=cpu[0].nbytes,static_bytes=bytes_of(plan),captured_boundary_bytes=bytes_of(b),
                connectivity_elements=int(len(bindings['live'])*len(plan['ports'])*b['slots'].size),
                cpu_encode_seconds=cpu_seconds,upload_seconds=upload,gpu_compile_first_seconds=first,gpu_warm_seconds=warm,readback_seconds=readback))
    out=dict(scope='first accepted block per rule, boundary encoding only',capture_sha256=meta['capture']['artifact_sha256'],blocks=results,
        limitations=['No isolated speedup claim; warm launch excludes upload/compilation','Capture already projected owner slots; gather and lifecycle costs remain in end-to-end execution report','Connectivity is currently dense and must be charged, not described as a free token operation','Readback is diagnostic; production token flow should remain resident'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
