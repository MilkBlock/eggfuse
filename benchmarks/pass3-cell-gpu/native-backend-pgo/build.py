"""Build, collect separate disjoint donor profiles, verify PGO in linked runtime IR."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from time import perf_counter
from pgo_common import BASE_REV,DONORS,HERE,ROOT,file_digest,inputs

ARCH = 'aarch64-apple-darwin'
NATIVE = Path('benchmarks/pass3-cell-gpu/compact-recipes/native')


def capture(args,**kwargs):
    return subprocess.check_output(args,text=True,**kwargs).strip()


def sources(a):
    # Reproduce this source tree with the composed-cpu/build.py recipe before running this study.
    learned = a.exp/'composed-cpu-profile-v1'
    build = json.loads((learned/'build.json').read_bytes())
    assert build['base']=='31bf7e41' and set(('lazy-equation-ports','published-single-headers')).issubset(build['extensions'])
    vanilla = a.out/'vanilla-src'
    vanilla.mkdir()
    cmd = ['git','archive',BASE_REV,'engine/cell-runtime','engine/structural-key',str(NATIVE)]
    with subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE) as proc:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:archive.extractall(vanilla,filter='data')
        assert proc.wait()==0
    return {
        'vanilla': (vanilla/NATIVE, ['--bin','eggfuse-vanilla-benchmark'], 'eggfuse-vanilla-benchmark'),
        'learned': (learned/'tree', ['-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--example','joint_witness_session'], 'examples/joint_witness_session'),
    }


def inspect_ir(dest):
    modules = list((dest/ARCH/'release/deps').glob('eggfuse_cell_runtime*.ll'))
    assert modules, dest
    total=positive=0
    accounts={}
    for m in modules:
        entries=[];counts={}
        for line in m.open():
            if line.startswith('define '):
                total+=1
                match=re.search(r'@([^ (]+).*?!prof !(\d+)',line)
                if match: entries.append(match.groups())
            elif '!"function_entry_count"' in line:
                match=re.search(r'^!(\d+) = !\{!"function_entry_count", i64 (\d+)',line)
                if match:counts[match.group(1)]=int(match.group(2))
        for symbol,id_ in entries:
            n=counts.get(id_,0)
            if n<=0: continue
            positive+=1
            for group,terms in {'execution':('Executor','execute'), 'graph':('graph','Graph'),
                                'multi-parent':('ordinary_witness',),'single-parent':('single_witness',)}.items():
                if all(t in symbol for t in terms):
                    g=accounts.setdefault(group,dict(positive_functions=0,max_entry_count=0,symbol=''))
                    g['positive_functions']+=1
                    if n>g['max_entry_count']:
                        g.update(max_entry_count=n,symbol=symbol)
    return dict(modules=len(modules),functions=total,positive_entry_functions=positive,accounts=accounts)


def compile_one(a,kind,mode,entry):
    cwd,options,exe=entry
    dest=a.out/f'{kind}-{mode}-target'; profile=a.out/kind/'donors.profdata'
    flags=[]
    if mode=='generate': flags=['-Cprofile-generate']
    if mode=='use':flags=[f'-Cprofile-use={profile}']
    env={k:v for k,v in os.environ.items() if k not in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','LLVM_PROFILE_FILE','RUSTC_WRAPPER')}
    env.update(CARGO_ENCODED_RUSTFLAGS='\x1f'.join(flags),CARGO_TARGET_DIR=str(dest),RUSTC_WRAPPER=str(HERE/'ir-wrapper.py'))
    cmd=['cargo','build','--offline','--locked','--release','--target',ARCH,*options]
    log=a.out/f'{kind}-{mode}.log';start=perf_counter()
    with log.open('w') as f:subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    binary=a.out/f'{kind}-{mode}';shutil.copyfile(dest/ARCH/'release'/exe,binary);binary.chmod(0o755)
    content=log.read_text();warnings=[x.strip() for x in content.splitlines() if re.search(r'profile.*(out of date|mismatch|discard|not found)|instrprof:|malformed.*profile',x,re.I)]
    if warnings:raise RuntimeError('\n'.join(warnings[:8]))
    ir=inspect_ir(dest)
    if mode=='use':
        assert ir['positive_entry_functions']>100 and 'graph' in ir['accounts'],(kind,ir)
        if kind=='learned':assert 'multi-parent' in ir['accounts'] and 'single-parent' in ir['accounts'],ir
    if mode=='plain':assert ir['positive_entry_functions']==0
    info=dict(sha256=file_digest(binary),bytes=binary.stat().st_size,seconds=round(perf_counter()-start,2),
              flags=[s.replace(str(a.out),'$OUT') for s in flags],profile_warnings=warnings,ir=ir)
    print(kind,mode,ir['positive_entry_functions'],info['seconds'],flush=True)
    return info


def train(a,kind,progdata):
    directory=a.out/kind;directory.mkdir()
    traces={}
    for name in DONORS:
        program,plans,cfg=progdata[name]
        cmd=[a.out/f'{kind}-generate',program]
        cfg=cfg if kind=='learned' else {}
        if kind=='learned':cmd.append(plans)
        raw=directory/f'{name}.profraw'
        out=subprocess.run(cmd,env=dict(os.environ,LLVM_PROFILE_FILE=str(raw)),input=(json.dumps(cfg)+'\n')*3,text=True,capture_output=True,check=True)
        records=[json.loads(v) for v in out.stdout.splitlines()]
        endpoints={(r['runs'],r['state_sha'],(r['multi']['total_rhs'] if kind=='learned' else r['rhs_count'])) for r in records}
        assert len(records)==3 and len(endpoints)==1 and raw.stat().st_size>0
        runs,graph,rhs=endpoints.pop()
        traces[name]=dict(runs=runs,state=graph,rhs=rhs,repetitions=len(records),raw_sha256=file_digest(raw),raw_bytes=raw.stat().st_size)
    profile=directory/'donors.profdata'
    subprocess.run([a.profdata,'merge','-o',profile,*[directory/(n+'.profraw') for n in DONORS]],check=True)
    info=capture([a.profdata,'show',profile])
    counted=int(re.search(r'Total functions: (\d+)',info).group(1))
    assert counted>100
    return dict(programs=traces,functions=counted,profile_sha256=file_digest(profile),profile_bytes=profile.stat().st_size)


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    a.profdata=capture(['xcrun','--find','llvm-profdata'])
    data={name:inputs(a,name) for name in DONORS}
    entries=sources(a)
    info=dict(rust=capture(['rustc','-vV']),profdata=capture([a.profdata,'--version']),host=capture(['uname','-m']),base=BASE_REV,
              learned_source_recipe=file_digest(a.exp/'composed-cpu-profile-v1/build.json'),binaries={},donors={})
    summary=a.out/'build.json'
    for kind,entry in entries.items():
        for mode in ('plain','generate','use'):
            if mode=='use':info['donors'][kind]=train(a,kind,data)
            info['binaries'][kind+'-'+mode]=compile_one(a,kind,mode,entry)
            summary.write_text(json.dumps(info,indent=1)+'\n')
    for name in DONORS:
        x,y=(info['donors'][k]['programs'][name] for k in ('vanilla','learned'))
        assert all(x[f]==y[f] for f in ('runs','state','rhs'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;main(a)
