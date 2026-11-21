"""Archive byte-exact native evidence as deduplicated UTF-8 text and a separately versioned trust index."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def fingerprint(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
def read(p):return json.loads(p.read_bytes())
def archive(raw,origins,out):
    ev=read(raw/'evidence.json');blobs={};trust=dict(schema='eggfuse-ripsat-donor-trust/v1',
        manifest_sha256=sha((raw/'evidence.json').read_bytes()),binary_sha256=ev['binary_sha256'],donors={},samples={})
    for donor,data in ev['donors'].items():
        trust['donors'][donor]=dict(captured_origins_sha256=sha((origins/(donor+'.json')).read_bytes()),program_sha256=data['program_sha256'],
                                   recipe_sha256=data['recipe_sha256'],source_parts=data['source_parts'])
        for sample in data['samples']:
            sid=sample['sample_id'];files=sample['artifacts']
            for name,file in files.items():
                assert file['path']==f'samples/{sid}/{name}' and '..' not in Path(name).parts and not Path(name).is_absolute()
                b=(raw/file['path']).read_bytes();assert sha(b)==file['sha256'];blobs[file['sha256']]=b.decode()
            acceptance=files.get('native/acceptance.json')
            if acceptance:
                receipt=read(raw/acceptance['path']);assert receipt==sample['native_acceptance']
                for path,h in receipt['artifact_sha256'].items():assert files['native/'+path]['sha256']==h,(sid,path)
            assert 'origin.json' in files
            trust['samples'][sid]=dict(sample_sha256=fingerprint(sample),origin_sha256=files['origin.json']['sha256'],
                                       acceptance_sha256=acceptance['sha256'] if acceptance else None)
    for n,v in [('trust.json',trust),('native-text.json',blobs)]:
        (out/n).write_text(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
    (out/'evidence.json').write_bytes((raw/'evidence.json').read_bytes())

def unpack(src,out):
    if out.exists():raise ValueError('choose a fresh destination')
    out.mkdir(parents=True)
    ev=read(src/'evidence.json');blobs=read(src/'native-text.json');trust=read(src/'trust.json')
    assert sha((src/'evidence.json').read_bytes())==trust['manifest_sha256']
    for d in ev['donors'].values():
        for i in d['samples']:
            assert fingerprint(i)==trust['samples'][i['sample_id']]['sample_sha256']
            for name,f in i['artifacts'].items():
                assert f['path']==f"samples/{i['sample_id']}/{name}" and '..' not in Path(name).parts and not Path(name).is_absolute()
                file=out/f['path'];data=blobs[f['sha256']].encode();assert sha(data)==f['sha256']
                file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
    (out/'evidence.json').write_bytes((src/'evidence.json').read_bytes())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('archive');a.add_argument('raw',type=Path);a.add_argument('origins',type=Path);a.add_argument('out',type=Path)
    u=sub.add_parser('unpack');u.add_argument('out',type=Path)
    a=p.parse_args()
    if a.mode=='archive':archive(a.raw,a.origins,a.out)
    else:unpack(HERE,a.out)
