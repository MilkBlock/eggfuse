"""Capture genuine pre-union boundaries, retaining program-level split provenance."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from collect_observed_corpus import read_bytes


def boundary(trace,rid):
    rule=trace['recipe']['rules'][rid]
    if any(o['kind'] not in ('copy','union') for o in rule['effects']):raise ValueError('unsupported selection rule')
    for run in trace['runs']:
        for b in run['audit']['bindings']:
            if b['rule']!=rid:continue
            values={p['slot']:p['before'] for p in b['eq_ports']}
            for op in rule['effects']:
                if op['kind']=='copy':values[op['dst']]=values.get(op['arg']['slot'])
                elif op['kind']=='union':
                    a,c=[values.get(v['slot']) for v in op['args']]
                    if a is not None and c is not None and a!=c:return run['ordinal']-1
    return None


def main():
    p=argparse.ArgumentParser()
    for k in ('training','validation','corpus','binary','model','artifacts','output'):p.add_argument(k,type=Path)
    p.add_argument('--capacity',type=int,default=128);p.add_argument('--reuse-snapshots',action='store_true')
    p.add_argument('--per-partition',type=int,default=2);p.add_argument('--rule',type=int,default=283);a=p.parse_args()
    if a.per_partition<1:raise ValueError('positive case count required')
    corpus=json.loads(a.corpus.read_text());sha=hashlib.sha256(a.corpus.read_bytes()).hexdigest();byname={c['case']:c for c in corpus['cases']}
    a.artifacts.mkdir(parents=True,exist_ok=True);records=[]
    for split,path in [('train',a.training),('validation',a.validation)]:
        manifest=json.loads(path.read_text());selected=0
        if manifest['partition']!=split or manifest['manifest_sha256']!=sha:raise ValueError('partition provenance')
        for c in manifest['cases']:
            if c['status']!='complete':continue
            raw=read_bytes(Path(c['trace']))
            if hashlib.sha256(raw).hexdigest()!=c['trace_sha256'] or c['split']!=split:raise ValueError('trace provenance')
            trace=json.loads(raw);at=boundary(trace,a.rule)
            if at is None:continue
            # Bound collection by already measured reference execution, not capture overhead.
            ref=trace.get('reference_execution_seconds')
            if ref is None or not 0<=ref<=1:continue
            name=c['case'];original=byname[name]
            if original['split']!=split or original['program_sha256']!=c['program_sha256']:raise ValueError('program partition')
            stem=a.artifacts/(split+'-'+name);snap=stem.with_suffix('.trace.json');result=stem.with_suffix('.result.json');archive=stem.with_suffix('.npz')
            program=stem.with_suffix('.program.json');program_raw=read_bytes(Path(original['program']))
            if json.loads(program_raw)['sha256']!=c['program_sha256']:raise ValueError('program fingerprint')
            program.write_bytes(program_raw)
            cmds=[[str(a.binary),str(program),str(snap),'--snapshot-runs='+str(at)],
                  [sys.executable,str(Path(__file__).with_name('audit_union_family.py')),str(snap),str(a.model),str(result),'--capacity',str(a.capacity),'--rule',str(a.rule),'--snapshot-run',str(at),'--capture',str(archive),'--corpus-manifest',str(a.corpus)]]
            if a.reuse_snapshots and snap.exists():
                old=json.loads(snap.read_text())
                if old['program_sha256']!=c['program_sha256'] or old['recipe']!=json.loads(program_raw)['recipe'] or not all(old.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')) or sum(b['ordinal']==at for b in old['boundaries'])!=1:raise ValueError('cached boundary provenance')
                cmds=cmds[1:]
            record=dict(case=name,partition=split,snapshot_run=at,rule=a.rule,capacity=a.capacity,status='verified',source_trace_sha256=c['trace_sha256'])
            logs=[]
            for cmd in cmds:
                process=subprocess.run(cmd,capture_output=True,text=True);logs.append(process.stdout+process.stderr)
                if process.returncode:
                    record.update(status='needs_investigation',exit_code=process.returncode);break
            stem.with_suffix('.log').write_text('\n'.join(logs))
            if record['status']=='verified':
                data=json.loads(result.read_text())
                if not data['passed'] or data['capture']['partition']!=split:raise ValueError('acceptance')
                record.update(capture=str(archive),result=str(result),samples=data['capture']['samples'],artifact_sha256=data['capture']['artifact_sha256'])
            records.append(record);print(json.dumps(record),flush=True);selected+=1
            if selected>=a.per_partition:break
    report=dict(scope='program-separated actual union snapshot corpus, not full Eggcc',records=records,corpus_manifest_sha256=sha,
        model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),capture_binary_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(),
        passed=len(records)==2*a.per_partition and all(r['status']=='verified' for r in records))
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
