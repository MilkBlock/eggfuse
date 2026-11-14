"""Run audited, terminating enumerated interfaces through the GPU token loop."""
import argparse,json,hashlib,sys,tarfile,tempfile,subprocess
from pathlib import Path
from collect_enumerated_native import archive_case,execute
from synthetic_cell_inputs import validate


def main():
    p=argparse.ArgumentParser()
    for key in ('native','model','head','output'):p.add_argument(key,type=Path)
    p.add_argument('--resume',action='store_true');p.add_argument('--producer-frames',action='store_true');a=p.parse_args()
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    native=json.loads((a.native/'manifest.json').read_text());head=json.loads(a.head.with_suffix('.json').read_text())
    if head['head_sha256']!=sha(a.head) or not head.get('synthetic_only_training'):raise ValueError('synthetic-only parent head required')
    report=dict(producer_frames=a.producer_frames,scope='enumerated terminating-boundary GPU feedback and CPU labels; no full Eggcc claim',native_manifest_sha256=sha(a.native/'manifest.json'),model_sha256=sha(a.model),head_sha256=sha(a.head),expected=sum(r['status']=='pass' for r in native['records']),records=[])
    a.output.mkdir(parents=True,exist_ok=a.resume)
    if a.resume:
        old=json.loads((a.output/'manifest.json').read_text())
        if bool(old.get('producer_frames',False))!=a.producer_frames:raise ValueError('resume initialization mode changed')
        for key in ('native_manifest_sha256','model_sha256','head_sha256','expected'):
            if old[key]!=report[key]:raise ValueError('resume identity changed')
        for row in old['records']:
            if sha(a.output/(str(row['index'])+'.tar.gz'))!=row['archive_sha256']:raise ValueError('archive changed')
        report=old
    done={r['index'] for r in report['records']}
    def save():
        tmp=a.output/'manifest.next.json';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.output/'manifest.json')
    save();scripts=Path(__file__).resolve().parent
    for source in native['records']:
        if source['status']!='pass' or source['index'] in done:continue
        archive=a.native/(str(source['index'])+'.tar.gz')
        if sha(archive)!=source['archive_sha256']:raise ValueError('native archive changed')
        row=dict(index=source['index'],input_sha256=source['input_sha256'],status='pending')
        with tempfile.TemporaryDirectory(prefix='eggfuse-enum-gpu-') as tmp:
            folder=Path(tmp);doc=folder/'input.json'
            with tarfile.open(archive) as t:doc.write_bytes(t.extractfile('case/input.json').read())
            validate(json.loads(doc.read_text()))
            commands=[
                [sys.executable,str(scripts/'audit_construct_union_family.py'),str(doc),str(a.model),str(folder/'execution.json'),'--synthetic-input','--rules','0,1,2','--snapshot-run','0','--capacity','32','--ticks','20','--flush-every','1','--order-queries','--boundary-context','--experimental-boundary-model','--predicted-source-feedback','--completion-classifier',str(a.head),'--completion-classifier-report',str(a.head.with_suffix('.json')),'--capture',str(folder/'capture.npz')],
                [sys.executable,str(scripts/'label_composed_witnesses.py'),str(folder/'capture.npz'),str(doc),str(a.model),'/dev/null',str(folder/'labeled.npz'),str(folder/'labels.json'),'--synthetic-input','--snapshot-run','0','--completion-classifier',str(a.head)]]
            if a.producer_frames:commands[0].append('--producer-frames')
            for phase,cmd in enumerate(commands):
                try:
                    with (folder/(str(phase)+'.log')).open('w') as log:result=execute(cmd,log,60)
                except subprocess.TimeoutExpired:row.update(status='timeout',phase=phase);break
                if result.returncode:row.update(status='failed',phase=phase,exit_code=result.returncode);break
            else:
                e=json.loads((folder/'execution.json').read_text());labels=json.loads((folder/'labels.json').read_text())
                if not e['passed'] or not labels['passed'] or not labels.get('synthetic_input'):raise ValueError('GPU/label audit failed')
                metadata=json.loads((folder/'labeled.json').read_text())
                if metadata['capture']!=labels or labels['artifact_sha256']!=sha(folder/'labeled.npz'):raise ValueError('training metadata mismatch')
                row.update(status='pass',samples=labels['samples'],generated_source_consumers=labels['continued_samples'],released_owner_rows=e['released_owner_rows'],labels_sha256=sha(folder/'labeled.npz'))
            row['archive_sha256']=archive_case(folder,a.output/(str(source['index'])+'.tar.gz'))
        report['records'].append(row);save()
        if len(report['records'])%10==0 or row['status']!='pass':print(json.dumps(dict(done=len(report['records']),expected=report['expected'],last=row)),flush=True)
    report['complete']=len(report['records'])==report['expected'] and all(r['status']=='pass' for r in report['records']);save()
    print(json.dumps(dict(complete=report['complete'],cases=len(report['records']))))
if __name__=='__main__':main()
