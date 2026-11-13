"""Compress only this collector's completed, newly owned JSON artifacts."""
import argparse
import gzip
import json
from pathlib import Path
import time


def archive(root):
    manifest=json.loads((root/'manifest.json').read_text());count=0
    for row in manifest['cases']:
        if row['status']!='complete':continue
        for name in ('program.json','relations.json'):
            path=root/row['case']/name
            if not path.exists():continue
            # Validate compressed bytes before deleting our redundant raw copy.
            data=path.read_bytes();dest=path.with_suffix(path.suffix+'.gz');temporary=dest.with_suffix('.tmp')
            temporary.write_bytes(gzip.compress(data,compresslevel=1,mtime=0))
            if gzip.decompress(temporary.read_bytes())!=data:raise ValueError('archive verification failed')
            temporary.replace(dest);path.unlink();count+=1
    return count,all(r['status']!='pending' for r in manifest['cases'])


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--watch',action='store_true');args=p.parse_args()
    while True:
        try:count,done=archive(args.root)
        except json.JSONDecodeError:count,done=0,False
        if count:print('archived',count,flush=True)
        if done or not args.watch:break
        time.sleep(2)

if __name__=='__main__':main()
