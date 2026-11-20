"""Produce real offline compound-action targets with entire program families segregated."""
import argparse
import json
from pathlib import Path
from compose_ceiling import study


def read(path):
    return json.loads(path.read_text())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--splits',nargs='+',choices=('train','development'),default=['train','development'])
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    summary={}
    donor=read(a.ref/'sum-bits/program.json')
    for name,item in read(a.corpus/'collection.json').items():
        split=item['split']
        if split not in a.splits:continue
        program=a.corpus/name/'program.json';image=a.corpus/name/'input'
        folder=a.out/split
        folder.mkdir(exist_ok=True)
        result=study(a.capture/name,donor,read(program),read(image/'ingress.json'),label_path=folder/f'{name}.npz')
        summary[name]=dict(split=split,paths=result['candidate_paths'],rhs=result['rhs'],
                           checked_spine_inputs=result['spine_receipts_checked'])
        (a.out/'manifest.json').write_text(json.dumps(summary,indent=1)+'\n')
        print(name,summary[name],flush=True)
