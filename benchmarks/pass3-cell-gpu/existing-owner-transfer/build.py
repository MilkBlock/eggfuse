"""Add an optional real storage intervention to an isolated copy of the pinned native Cell engine."""
import argparse
from pathlib import Path
import shutil
import subprocess
import os
HERE=Path(__file__).resolve().parent

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('legacy',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);tree=a.out/'tree'
    subprocess.run(['cp','-cR',a.legacy/'legacy',tree],check=True)
    src=tree/'engine/cell-runtime/src'
    for source,dest in [('store.rs','completed_owner_store.rs'),('graph.rs','shared_owner_transfer.rs')]:
        name='old_pair_'+source
        shutil.copyfile(HERE/source,src/name)
        with (src/dest).open('a') as f:f.write('\ninclude!("'+name+'");\n')
    # The pinned transfer audit predates the current generic event log. Capture the same
    # committed (hi, lo) pair after canonical equality is established, outside proof stamps.
    graph=src/'graph.rs';text=graph.read_text();mark='        let (lo, hi) = (a.min(b), a.max(b));'
    assert text.count(mark)==1
    graph.write_text(text.replace(mark,mark+'\n        crate::transfer_audit::trial_union(hi,lo);'))
    with (src/'transfer_audit.rs').open('a') as f:
        f.write('''
thread_local! {static OWNER_TRIAL_UNIONS:std::cell::RefCell<Vec<serde_json::Value>>=const{std::cell::RefCell::new(Vec::new())};}
pub(crate) fn trial_union(hi:u64,lo:u64){OWNER_TRIAL_UNIONS.with_borrow_mut(|v|v.push(serde_json::json!(["union",hi,lo])));}
pub fn take_trial_unions()->Vec<serde_json::Value>{OWNER_TRIAL_UNIONS.take()}
''')
    shutil.copyfile(HERE/'driver.rs',tree/'tools/cell-compiler/examples/existing_owner_transfer.rs')
    env=dict(os.environ,CARGO_TARGET_DIR=str(a.out/'target'))
    subprocess.run(['cargo','build','--offline','--locked','--release','-p','eggfuse-cell-compiler','--features','iterative-bake,sparse-cells,storage-metrics','--example','existing_owner_transfer'],cwd=tree,env=env,check=True)
    shutil.copyfile(a.out/'target/release/examples/existing_owner_transfer',a.out/'engine')
    (a.out/'engine').chmod(0o755)
