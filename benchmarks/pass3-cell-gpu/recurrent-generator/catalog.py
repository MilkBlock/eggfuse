"""Transfer only typed, certified leaves. No inference input comes from an execution trace."""
import hashlib
import json
from pathlib import Path
import numpy as np

def read(path):
    return json.loads(path.read_bytes())

def load_catalog(image, program, donor):
    packet=read(image/'ingress.json'); spec=read(image/'device.json')
    if packet['program_sha256']!=hashlib.sha256(program.read_bytes()).hexdigest():
        raise ValueError('image/program mismatch')
    target=read(program); source=read(donor)
    if source['recipe']['tables']!=target['recipe']['tables']:raise ValueError('different schemas')
    with np.load(image/'device.npz') as arrays:rom=arrays['rom']
    layout=spec['layout'];records=[]
    for leaf in source['spine_blocks']['entries']:
        rid,pivot=leaf['consumer'],leaf['pivot']
        left,right=(p['recipe']['rules'][rid] for p in (source,target))
        # All decisions are tied to the typed source rule and the local compiler certificate.
        if not all(left[k]==right[k] for k in ('query','effects','slots')) or not any(
            e['rule']==rid and e['anchor']==pivot for e in packet['stage_entries']
        ):
            records.append([-1,0,0,0]);continue
        n,start,_,_=map(int,rom[layout['SPINE']+4*rid:][:4])
        paths=[int(path) for pos,path in rom[start:start+2*n].reshape(-1,2) if pos==pivot]
        assert len(paths)==1
        path=paths[0];records.append([rid,pivot,path,int(rom[path])])
    return records

def validate_device_contracts(image,entries):
    spec=read(image/'device.json')
    with np.load(image/'device.npz',allow_pickle=False) as packed:rom=packed['rom']
    layout=spec['layout'];seen=set()
    for rid,pivot,path,table in entries:
        if rid<0:
            if [rid,pivot,path,table]!=[-1,0,0,0]:raise ValueError('invalid absent template')
            continue
        if not 0<=rid<layout['RULES'] or (rid,pivot) in seen:raise ValueError('invalid recurrent leaf')
        seen.add((rid,pivot))
        n,at,_,_=map(int,rom[layout['SPINE']+4*rid:][:4])
        if [pivot,path] not in rom[at:at+2*n].reshape(-1,2).tolist() or int(rom[path])!=table:
            raise ValueError('unproved route in recurrent leaf bank')
