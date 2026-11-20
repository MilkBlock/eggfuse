"""Apply the reviewed unmarked-native acceptance contracts to real notified GPU exports."""
import argparse,json,subprocess,sys
from pathlib import Path
from replay import execute,plans,GPU

def check(ref,weights,out):
    out.mkdir(parents=True,exist_ok=False)
    for case in ('sum-bits','dot-product'):
        plan,_=plans(ref,case,'sum-bits')
        execute(ref/f'release-input-{case}/device.json',weights,ref/'ports-1703.pt',2048,2,out/f'export-{case}',
                block_study=dict(plan,select=True,notify=True),export_only=True)
        (out/case).symlink_to(ref/case)
    s=out/'native-gpu-sum';s.mkdir()
    for name in ('sum-legacy','run-values','native-source.json','native-legacy.json','native-values.json'):
        (s/name).symlink_to((ref/'native-gpu-sum'/name).resolve())
    (s/'run-legacy').symlink_to(out/'export-sum-bits')
    subprocess.run([sys.executable,GPU.parent/'marker-handoff/choice_diagnosis.py',s,s/'check.json'],check=True)
    (out/'native-gpu-dot').symlink_to(ref/'native-gpu-dot')
    subprocess.run([sys.executable,GPU/'native_accept.py',out,out/'dot-check.json'],check=True)
    return [json.loads(p.read_text())['status'] for p in (s/'check.json',out/'dot-check.json')]

if __name__=='__main__':
    q=argparse.ArgumentParser()
    for name in ('reference','weights','out'):q.add_argument(name,type=Path)
    a=q.parse_args()
    assert check(a.reference.resolve(),a.weights.resolve(),a.out.resolve())==['pass','pass']
