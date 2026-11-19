"""Offline Bake, isolated GPU launches, independent audits, then equal-correctness timing."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def reproduce(root,address):
    root.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTORCH_ENABLE_MPS_FALLBACK='0')
    def run(*args):
        subprocess.run(list(map(str,args)),cwd=REPO,env=env,check=True)
    def py(file,*args):run(sys.executable,HERE/file,*args)
    def cargo(*args):run('cargo',*args)
    runtime=Path(env.get('CARGO_TARGET_DIR',str(REPO/'target')))/'release/eggfuse-cell-runtime'
    native=runtime.parent/'examples/marker_reference'
    out=root/'results';out.mkdir()
    py('ports.py',root/'ports-1703.pt')
    for s in (1703,1709):py('routing.py',root/f'router-{s}.pt',s)
    names=('sum-bits','dot-product')
    for name in names:
        cargo('cell-compile','--case',name,'--output',root/name)
        packet=root/f'release-input-{name}'
        py('codec.py',root/name/'program.json',packet);py('lower.py',packet/'ingress.json')
        def launch(folder,*flags):
            py('run.py',packet/'device.json',address,root/folder,'--port-weights',root/'ports-1703.pt',*flags)
        launch(f'release-{name}')
        launch(f'release-one-{name}','--rows',1,'--tiles',64)
        for s in (1703,1709):launch(f'release-{name}-learned-{s}','--router',root/f'router-{s}.pt')
        launch(f'export-{name}','--export-only')

    # Only after the online executions finish, generate independent references.
    cargo('build','--release','--locked','-p','eggfuse-cell-runtime','--features','slot-transfer-audit')
    for name in names:
        program=root/name/'program.json';oracle=root/f'oracle-{name}';events=root/f'events-lifecycle-{name}'
        run(runtime,'--program',program,'--output',oracle,'--audit-stages')
        run(runtime,'--program',program,'--output',events,'--audit-events')
        for lane in (f'release-{name}',f'release-one-{name}',*(f'release-{name}-learned-{s}' for s in (1703,1709))):
            folder=root/lane;packet=root/f'release-input-{name}'/'ingress.json'
            py('events_audit.py',program,packet,folder,oracle,events,folder/'ordered.json')
            py('endpoint.py',packet,folder,oracle,folder/'check.json','--ordered',folder/'ordered.json')
    cargo('build','--release','--locked','-p','eggfuse-cell-compiler','--example','marker_reference')
    for n,label in zip(names,('sum','dot')):
        folder=root/f'native-gpu-{label}';folder.mkdir()
        for source,dest in [('source_sk.egg','native-source.json'),('source_sk_mk.egg','native-legacy.json')]:
            run(native,root/n/source,folder/dest)
    folder=root/'native-gpu-sum'
    (folder/'sum-legacy').symlink_to(root/'sum-bits',target_is_directory=True)
    (folder/'run-legacy').symlink_to(root/'export-sum-bits',target_is_directory=True)
    cargo('cell-compile','--source',root/'sum-bits/source.egg','--bake-source',root/'sum-bits/bake-source.egg',
          '--marker-handoff','values','--output',folder/'sum-values')
    run(native,folder/'sum-values/source_sk_mk.egg',folder/'native-values.json')
    run(runtime,'--program',folder/'sum-values/program.json','--output',folder/'run-values')
    run(sys.executable,HERE.parent/'marker-handoff/choice_diagnosis.py',folder,folder/'check.json')
    py('native_accept.py',root,root/'native-gpu-dot/check.json')
    cargo('build','--release','--locked','-p','eggfuse-cell-runtime')
    py('isolated_check.py',root,address,out/'isolated.json')
    py('primitive_audit.py',out/'typed-scalars.json')
    py('cli_bench.py',root,address,runtime,out/'cli.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('fresh_output',type=Path);p.add_argument('frozen_packed_weights',type=Path)
    a=p.parse_args();reproduce(a.fresh_output.resolve(),a.frozen_packed_weights.resolve())
