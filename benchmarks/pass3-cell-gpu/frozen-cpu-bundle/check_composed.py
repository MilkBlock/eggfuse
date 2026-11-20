"""Run relocated composed bundles from native compilation, then compare with measured source and Cell ledgers."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
from check import cli
from check_native import locations

HERE=Path(__file__).resolve().parent
read=lambda f:json.loads(f.read_bytes())
digest=lambda b:hashlib.sha256(b).hexdigest()


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    expected={}
    for f in ('core.json','large.json'):
        expected.update(read(HERE.parent/'composed-cpu'/f))
    env={k:v for k,v in os.environ.items() if not k.startswith('EGGFUSE_')}
    result={}
    for name,variants in expected.items():
        src,_=locations(a.exp,name);dest=a.out/(name+'-compiled')
        args=[a.native,'--compile-bundle',src,dest,'--profile','composed-ports/v1']
        with tempfile.TemporaryDirectory() as cwd:
            subprocess.run(args,cwd=cwd,env=env,check=True)
            relocated=a.out/(name+' moved')
            dest.rename(relocated)
            native=cli(a.native,'--bundle',relocated,cwd);assert native.returncode==0,native.stderr
            v=json.loads(native.stdout);ref=variants['combined-lazy']
            assert v['state_sha']==ref['state_sha'] and v['neural_rhs']==v['rhs']==variants['vanilla']['rhs']
            assert v['remaining_rhs']==0 and v['runs']==variants['vanilla']['runs'] and v['root_cells_allocated']==ref['root_allocated']
            ev=v['profile_execution'];assert v['cpu_profile']=='composed-ports/v1' and ev['views']==2 and ev['sealed_before_verifier']
            assert v['multi_raw_tuples']==ev['sealed_tuples']==ref['counts']['raw_tuples']
            for signal,gold in [('published_header_updates',ref['header']['delta_updates']),
                                ('lazy_arithmetic_evaluations',ref['lazy']['computed']),('signature_cache_hits',ref['lazy']['table_hits'])]:
                assert 0<ev[signal]==gold,(name,signal,ev[signal],gold)
            frozen=a.exp/'frozen-native-plans-parity-v2'/name/'rust-1703'
            common=['program.json','plans.json','ports.bin','single.json','multi.json','merge.json','root.json']
            assert all((relocated/f).read_bytes()==(frozen/f).read_bytes() for f in common)
            row=dict(common_files=len(common),rhs=v['rhs'],runs=v['runs'],state=v['state_sha'],root_allocated=v['root_cells_allocated'],execution=ev)
            if name in ('sum-bits','conjugate-gradient'):
                audit=cli(a.native,'--audit-bundle',relocated,cwd);assert audit.returncode==0,audit.stderr
                actual=json.loads(audit.stdout)
                truth=json.loads(subprocess.run([a.exp/'compact-vanilla-20261121/vanilla-audit',src],
                        input='{"audit":true}\n',text=True,capture_output=True,check=True,cwd=cwd).stdout)
                assert all(actual[k]==truth[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha'))
                assert [[e for e in run if e[0]=='union'] for run in actual['events']]==truth['unions']
                assert actual['multi']['raw_sha256']==ref['multi'] and actual['root_recipe']['raw_hash']==ref['raw']
                fresh=actual['cell_ids']
                assert hashlib.sha256(json.dumps(fresh,separators=(',',':'),sort_keys=True).encode()).hexdigest()==ref['cells']
                row['full_audit']=True
            if name=='sum-bits':
                plain=a.out/'default'
                subprocess.run([a.native,'--compile-bundle',src,plain],cwd=cwd,env=env,check=True)
                assert all((plain/f).read_bytes()==(frozen/f).read_bytes() for f in common+['request.json','bundle-manifest.json'])
                previous=cli(a.native,'--bundle',plain,cwd);assert previous.returncode==0
                old=json.loads(previous.stdout)
                assert old['cpu_profile']=='frozen-ports/v1' and old['multi_raw_tuples']==variants['off']['counts']['raw_tuples'] and old['state_sha']==v['state_sha']
                # Verify the executable's profile contract even if a caller regenerates the file hashes.
                for folder,value in [(relocated,0),(plain,4)]:
                    request=folder/'request.json';manifest=folder/'bundle-manifest.json'
                    orig=request.read_bytes();orig_manifest=manifest.read_bytes()
                    cfg=json.loads(orig);cfg['lazy_equations']=value
                    request.write_text(json.dumps(cfg));m=json.loads(orig_manifest);m['files']['request.json']=digest(request.read_bytes());manifest.write_text(json.dumps(m))
                    bad=cli(a.native,'--bundle',folder,cwd)
                    assert bad.returncode and 'profile' in bad.stderr
                    request.write_bytes(orig);manifest.write_bytes(orig_manifest)
                bad=subprocess.run([a.native,'--compile-bundle',src,a.out/'bad','--profile','unknown'],cwd=cwd,env=env,capture_output=True)
                assert bad.returncode and not (a.out/'bad').exists()
                row['default_profile_byte_identical']=True;row['mismatches_rejected']=3
        result[name]=row
        (a.out/'composed.json').write_text(json.dumps(result,indent=1)+'\n')
        print(name,v['rhs'],ev['sealed_tuples'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
