import argparse
import gzip
import json
from pathlib import Path
import subprocess

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for a in ('binary','bundle','out'):
        p.add_argument(a,type=Path)
    args=p.parse_args()
    run=subprocess.run([args.binary,args.bundle/'program.json',args.bundle/'plans.json'],
                       input='{"baseline":true}\n',text=True,capture_output=True,check=True)
    data=json.loads(run.stdout)
    if 'source_error' in data:
        raise ValueError(data['source_error'])
    with gzip.open(args.out,'wt') as stream:
        json.dump(data['join_inputs'],stream,separators=(',',':'))
    print(args.out,len(data['join_inputs']),data['state_sha'])
