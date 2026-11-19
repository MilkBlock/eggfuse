"""Separate codec generalization test on the two different GPU-produced first-Run graphs."""
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
from codec import packet
from lower import save_device_image
from reader import read
from probe_audit import replay


def study(root,address):
    results={}
    for name in ('sum-bits','dot-product'):
        # This process is an offline re-encoding experiment. Its outputs are
        # never fed back to the Pass 3 executor, which starts at the original input.
        base=json.loads((root/name/'program.json').read_text())
        strings=json.loads((root/f'prefix-{name}-2/run.json').read_text())['strings']
        with np.load(root/f'prefix-{name}-2/snapshots.npz') as z:
            facts=[]
            for m,row in zip(z['meta_1'],z['rows_1']):
                if m[3]==2:continue
                table=base['recipe']['tables'][m[0]]
                values=[]
                for spec,v in zip(table['schema'],row):
                    k=spec['kind'];v=int(v)
                    item=dict(sort=spec['name'])
                    if k=='eq':item['eq']=f'Gpu({v})'
                    else:item['value']=strings[v] if k=='String' else bool(v) if k=='bool' else v
                    values.append(item)
                facts.append(dict(table=table['name'],subsumed=bool(m[3]),values=values))
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'fixture.json';base['initial']=facts
            source.write_text(json.dumps(base));p=packet(source,folder)
            save_device_image(folder/'ingress.json',folder)
            ids=[i for i,v in enumerate(p['symbols']) if v['sort']=='BaseType' and 'eq' in v][:2]
            for join,file in [(None,'plain.npz'),(ids,'union.npz')]:
                read(folder/'device.json',address,root/'ports-1703.pt',folder/file,join)
            results[name]=replay(source,folder/'ingress.json',folder/'plain.npz',folder/'union.npz',ids)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','address','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(study(a.root,a.address),indent=1)+'\n')
