"""Post-training edge-distribution transfer. Outputs are never fed back into the compiler."""
import argparse,json,os,re,subprocess
from pathlib import Path
from pgo_common import HOLDOUTS,file_digest,inputs


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((a.build/'build.json').read_bytes())
    timed=json.loads((a.study/'results.json').read_bytes())
    tool=subprocess.check_output(['xcrun','--find','llvm-profdata'],text=True).strip()
    results={}
    for name in HOLDOUTS:
        program,plans,request=inputs(a,name)
        results[name]={}
        for kind in ('learned','vanilla'):
            donor=a.build/kind/'donors.profdata'; original=manifest['donors'][kind]['profile_sha256']
            assert file_digest(donor)==original
            raw=a.out/f'{name}-{kind}.profraw';profile=raw.with_suffix('.profdata')
            args=[a.build/f'{kind}-generate',program]
            cfg=request if kind=='learned' else {}
            if kind=='learned':args.append(plans)
            p=subprocess.run(args,input=json.dumps(cfg)+'\n',text=True,capture_output=True,check=True,
                             env=dict(os.environ,LLVM_PROFILE_FILE=str(raw)))
            obs=json.loads(p.stdout);truth=timed[name]['arms']['vanilla-release']
            assert obs['runs']==truth['runs'] and obs['state_sha']==truth['state_sha']
            assert (obs['multi']['total_rhs'] if kind=='learned' else obs['rhs_count'])==truth['rhs']
            subprocess.run([tool,'merge','-o',profile,raw],check=True)
            output=subprocess.check_output([tool,'overlap',donor,profile],text=True)
            match=lambda pat:re.search(pat,output).group(1)
            row=dict(edge_percent=float(match(r'Edge profile overlap: ([\d.]+)%')),
                     donor_edges=int(match(r'Edge profile base count sum: (\d+)')),
                     test_edges=int(match(r'Edge profile test count sum: (\d+)')),
                     overlap_functions=int(match(r'# of functions overlap: (\d+)')),
                     donor_sha256=original,heldout_sha256=file_digest(profile))
            assert file_digest(donor)==original
            results[name][kind]=row
            print(name,kind,row['edge_percent'],flush=True)
        (a.out/'overlap.json').write_text(json.dumps(results,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','study','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;measure(a)
