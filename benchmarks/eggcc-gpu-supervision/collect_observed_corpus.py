"""Capture many real eggcc workloads, preserving whole-workload partitions.

This collects CPU reference inputs for GPU research, not performance measurements.
Every failure remains in the manifest. No failed workload is silently dropped.
"""
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import subprocess
from observed_cell_targets import collect


def read_bytes(path):
    if path.exists():return path.read_bytes()
    return gzip.decompress(path.with_suffix(path.suffix+'.gz').read_bytes())


def exists(path):return path.exists() or path.with_suffix(path.suffix+'.gz').exists()


def digest(path):return hashlib.sha256(read_bytes(path)).hexdigest()


def split(case):
    fixed={'032-sum-bits':'train','020-loopfact':'train','016-gcd':'validation','010-dot-product':'test','012-fact':'test','018-is-decreasing':'test'}
    if case in fixed:return fixed[case]
    bucket=int(hashlib.sha256(case.encode()).hexdigest()[:8],16)%10
    return 'test' if bucket==0 else 'validation' if bucket==1 else 'train'


def role_features(rule,inputs,positions=False):
    """Pre-effect slot roles; copy aliases share roles. No completion labels."""
    env={int(slot):tuple(value) for slot,value in inputs};roles={}
    def record(arg,role):
        if 'slot' in arg and arg['slot'] in env:
            key=json.dumps(env[arg['slot']]);roles.setdefault(key,[]).append(role)
    for index,atom in enumerate(rule['query']):
        for pos,arg in enumerate(atom['args']):record(arg,('query',atom['call'],pos)+((index,) if positions else ()))
    operation=0
    for effect in rule['effects']:
        if effect['kind']=='copy':
            arg=effect['arg']
            value=env.get(arg.get('slot'))
            env.pop(effect['dst'],None)
            if value is not None:env[effect['dst']]=value
            continue
        for pos,arg in enumerate(effect.get('args',[])):record(arg,('effect',effect['kind'],effect.get('call',{}),pos)+((operation,) if positions else ()))
        if 'value' in effect:record(effect['value'],('effect-value',effect['kind'],effect.get('call',{}))+((operation,) if positions else ()))
        # Overwritten destinations no longer denote matched inputs.
        if 'dst' in effect:env.pop(effect['dst'],None)
        operation+=1
    return [{'port':json.loads(k),'roles':v} for k,v in sorted(roles.items())]


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path);p.add_argument('--bin',type=Path,default=Path('target/debug/examples'));p.add_argument('--cache',type=Path,action='append',default=[]);p.add_argument('--timeout',type=int,default=30);p.add_argument('--limit',type=int);args=p.parse_args()
    sources=sorted(args.capture.glob('*/pass-3-flat.egg'))
    if args.limit is not None:sources=sources[:args.limit]
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=dict(scope='CPU observed multi-entry inputs and conditional local labels; not GPU execution or timing study',partition='whole workload; fixed prior holdouts plus SHA256(case) modulo 10',tools={name:digest(args.bin/name) for name in ['emit_cell_source','gpu_supervision_live_trace']},cases=[dict(case=f.parent.name,split=split(f.parent.name),source=str(f.resolve()),source_sha256=digest(f),status='pending') for f in sources])
    destination=args.output/'manifest.json'
    def save():destination.write_text(json.dumps(manifest,indent=2)+'\n')
    save()
    for source,row in zip(sources,manifest['cases']):
        case=row['case'];dest=args.output/case;dest.mkdir(exist_ok=True)
        try:
            cached=None
            for root in [args.output]+args.cache:
                program=root/case/'program.json';trace=root/case/'relations.json';src=root/case/'source.egg'
                if exists(program) and exists(trace) and src.exists() and digest(src)==row['source_sha256']:
                    cached=(program,trace);break
            if cached:program_path,trace_path=cached
            else:
                program_path=dest/'program.json';trace_path=dest/'relations.json'
                with (dest/'capture.log').open('w') as log:
                    subprocess.run([str(args.bin/'emit_cell_source'),str(source),str(dest)],stdout=log,stderr=log,check=True,timeout=args.timeout)
                    subprocess.run([str(args.bin/'gpu_supervision_live_trace'),str(program_path),str(trace_path),'--relations'],stdout=log,stderr=log,check=True,timeout=args.timeout)
            program=json.loads(read_bytes(program_path));trace=json.loads(read_bytes(trace_path));data=collect(program,trace)
            if data['summary']['derived_input_equality_violations']:raise ValueError('native equality audit violation')
            for sample in data['targets']:sample['input_local_roles']=role_features(program['recipe']['rules'][sample['consumer']],sample['binding'])
            data.update(trace_sha256=digest(trace_path),case=case,split=row['split'])
            output=dest/'targets.json';output.write_text(json.dumps(data)+'\n')
            row.update(status='complete',program=str(program_path.resolve()),trace=str(trace_path.resolve()),trace_sha256=data['trace_sha256'],program_sha256=program['sha256'],targets=str(output.resolve()),targets_sha256=digest(output),summary=data['summary'],reused_trace=bool(cached))
        except (subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError,KeyError,OSError) as error:
            row.update(status='failed',error_type=type(error).__name__,error=str(error))
        save();print(json.dumps({k:row[k] for k in ('case','split','status','summary','error') if k in row}),flush=True)
    completed=[r for r in manifest['cases'] if r['status']=='complete']
    manifest['summary']=dict(workloads=len(sources),complete=len(completed),failed=len(sources)-len(completed),observed_bindings=sum(r['summary']['observed_bindings'] for r in completed),supported_bindings=sum(r['summary']['supported_bindings'] for r in completed),unique_states_per_workload_sum=sum(r['summary']['unique_states'] for r in completed),multi_state_rules_per_workload_sum=sum(r['summary']['rules_with_multiple_states'] for r in completed))
    save();print(json.dumps(manifest['summary']),flush=True)

if __name__=='__main__':main()
