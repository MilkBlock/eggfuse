"""Label every distinct enumerated boundary with audited native execution.

Failures/timeouts remain explicit. Never call an incomplete execution saturation.
"""
import argparse,hashlib,json,subprocess,tarfile,tempfile,os,signal
from pathlib import Path
from synthetic_cell_inputs import validate,digest
from synthetic_native_source import emit
from native_cell_examples import extract
from enumerated_boundary_labels import label


def execute(command,log,timeout):
    # Compiler may launch native Bake children; bound the entire process group.
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait();raise
    return process


def archive_case(folder,archive):
    hashes={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    with tarfile.open(archive,'w:gz') as t:t.add(folder,arcname='case')
    with tarfile.open(archive,'r:gz') as t:
        actual={str(Path(p.name).relative_to('case')):hashlib.sha256(t.extractfile(p).read()).hexdigest() for p in t.getmembers() if p.isfile()}
    if actual!=hashes:raise ValueError('archive verification failed')
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def run(directory,output,compiler,observer,compile_timeout=10.,run_timeout=1.,resume=False,retry_failed=False):
    manifest=json.loads((directory/'manifest.json').read_text());recipe=manifest['recipe']
    if digest(recipe)!=manifest['recipe_sha256']:raise ValueError('recipe checksum')
    stages=list(dict.fromkeys(r['metadata']['source_set'] for r in recipe['rules']))
    if len(stages)!=1:raise ValueError('explicit multistage policy required')
    schedule=dict(saturate=dict(run=stages[0]));groups={}
    documents=manifest.get('input_format')=='documents'
    input_path=directory/('documents.jsonl' if documents else 'cases.jsonl')
    for line in input_path.read_text().splitlines():
        case=json.loads(line)
        doc=case if documents else dict(schema='enumerated-cell-input/v1',recipe=recipe,recipe_sha256=digest(recipe),case=case,snapshot=case['snapshot'],input_sha256=case['input_sha256'])
        if doc['recipe']!=recipe:raise ValueError('input recipe mismatch')
        validate(doc);groups.setdefault(doc['input_sha256'],[]).append(doc)
    output.mkdir(parents=True,exist_ok=resume)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(scope='native labels for synthetic constructor boundaries; not GPU model training',compiler_sha256=sha(compiler),observer_sha256=sha(observer),enumeration_sha256=sha(input_path),source_control=schedule,expected_inputs=len(groups),records=[])
    if resume:
        previous=json.loads((output/'manifest.json').read_text())
        for key in ('compiler_sha256','observer_sha256','enumeration_sha256','source_control','expected_inputs'):
            if previous[key]!=report[key]:raise ValueError('resume provenance mismatch: '+key)
        for i,record in enumerate(previous['records']):
            if record['index']!=i or record['input_sha256']!=list(groups)[i]:raise ValueError('resume order mismatch')
            if sha(output/(str(i)+'.tar.gz'))!=record['archive_sha256']:raise ValueError('resume archive mismatch')
        report=previous
    def save():
        pending=output/'manifest.next.json'
        pending.write_text(json.dumps(report,indent=2)+'\n');pending.replace(output/'manifest.json')
    save()
    for index,(identity,docs) in enumerate(groups.items()):
        previous=None
        if index<len(report['records']):
            previous=report['records'][index]
            if not retry_failed or previous['status']=='pass':continue
            old=output/(str(index)+'.tar.gz')
            backup=output/(str(index)+'.previous-'+previous['archive_sha256']+'.tar.gz')
            if not backup.exists():backup.write_bytes(old.read_bytes())
        temporary=tempfile.TemporaryDirectory(prefix='eggfuse-enumerated-')
        folder=Path(temporary.name);source=folder/'input.egg';program=folder/'compiled/program.json';trace=folder/'trace.json'
        (folder/'input.json').write_text(json.dumps(docs[0])+'\n')
        (folder/'routes.json').write_text(json.dumps([d.get('case',d.get('generator')) for d in docs])+'\n')
        source.write_text(emit(docs[0],schedule))
        record=dict(index=index,input_sha256=identity,routes=len(docs),source_sha256=sha(source),status='pending')
        commands=[([str(compiler),'compile','--source',str(source),'--output',str(folder/'compiled')],compile_timeout),([str(observer),str(program),str(trace),'--relations','--snapshot-runs=0'],run_timeout)]
        for phase,(command,timeout) in enumerate(commands):
            try:
                with (folder/f'{phase}.log').open('w') as log:result=execute(command,log,timeout)
            except subprocess.TimeoutExpired:
                record.update(status='timeout',phase=phase);break
            if result.returncode:
                record.update(status='failed',phase=phase,exit_code=result.returncode);break
        else:
            try:
                t=json.loads(trace.read_text());p=json.loads(program.read_text())
                if t['program_sha256']!=p['sha256']:raise ValueError('program trace identity')
                examples=extract(t)
                boundary=label(docs[0],t)
                (folder/'boundary-labels.json').write_text(json.dumps(boundary)+'\n')
                (folder/'examples.json').write_text(json.dumps(examples)+'\n')
                record.update(status='pass',examples=len(examples['examples']),runs=len(t['runs']),program_sha256=p['sha256'],trace_sha256=sha(trace))
            except (ValueError,KeyError) as error:record.update(status='audit_failed',reason=str(error))
        record['archive_sha256']=archive_case(folder,output/(str(index)+'.tar.gz'))
        temporary.cleanup()
        if previous is not None:
            record['previous_attempt']=previous;report['records'][index]=record
        else:report['records'].append(record)
        save()
        if index%25==0:print(json.dumps(dict(done=index+1,total=len(groups))),flush=True)
    report['complete']=len(report['records'])==len(groups) and all(r['status']=='pass' for r in report['records']);save()
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['directory','output','compiler','observer']:p.add_argument(key,type=Path)
    p.add_argument('--resume',action='store_true');p.add_argument('--retry-failed',action='store_true');p.add_argument('--compile-timeout',type=float,default=10.);p.add_argument('--run-timeout',type=float,default=1.);a=p.parse_args()
    result=run(a.directory,a.output,a.compiler,a.observer,a.compile_timeout,a.run_timeout,a.resume,a.retry_failed)
    from collections import Counter
    print(json.dumps(dict(complete=result['complete'],statuses=dict(Counter(r['status'] for r in result['records'])))))
