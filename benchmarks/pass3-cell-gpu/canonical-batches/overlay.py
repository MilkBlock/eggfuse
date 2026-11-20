"""Add phase-scoped canonical equality batches to the pinned complete-generation CPU executor."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
def replace(p,old,new):
    s=p.read_text()
    if s.count(old)!=1:raise ValueError((p.name,old[:65],s.count(old)))
    p.write_text(s.replace(old,new))
def install(crate):
    src=crate/'src';p=src/'parent_epoch.rs'
    replace(p,'pub struct Parents {','pub struct Parents {\n    batch:CanonicalBatch,')
    replace(p,'pub fn insert(&mut self, id: u64, to: u64) -> Option<u64> {','pub fn insert(&mut self, id: u64, to: u64) -> Option<u64> {\n        self.batch.record(id,to);')
    replace(p,'        self.local.clear();','''        self.local.clear();self.batch.bits.clear();self.batch.cells.clear();self.batch.links.clear();
        if self.batch.flags().1{self.batch.stamp=next_stamp();}''')
    shutil.copyfile(HERE/'roots.rs',src/'canonical_batch.rs')
    with p.open('a') as f:f.write('\ninclude!("canonical_batch.rs");\n')
    p=src/'value.rs';s=p.read_text();begin=s.index('pub fn root(parents: &Parents, mut x: u64) -> u64 {');end=s.index('pub fn canon(',begin)
    p.write_text(s[:begin]+'#[inline]\npub fn root(parents:&Parents,x:u64)->u64{parents.selected_root(x)}\n'+s[end:])
    p=src/'runtime.rs'
    replace(p,'        let search_end = Instant::now();','        let search_end = Instant::now();\n        self.graph.parents.canonical_phase(1);')
    replace(p,'        let rhs_end = Instant::now();','        let rhs_end = Instant::now();\n        self.graph.parents.canonical_phase(2);')
    replace(p,'        let repair_end = Instant::now();','        let repair_end = Instant::now();\n        self.graph.parents.canonical_phase(0);')
    p=crate/'examples/joint_witness_session.rs'
    replace(p,'        let initial_cells = runtime.graph.stats.cells_created;', '''        runtime.graph.parents.configure_canonical_batch(
        u8::try_from(req["canon_mode"].as_u64().unwrap_or(0))?,u8::try_from(req["canon_scope"].as_u64().unwrap_or(6))?,
        req["canon_audit"]==true,req["canon_check"]==true)?;
        let initial_cells = runtime.graph.stats.cells_created;''')
    replace(p,'        report["root_recipe"]=', '        report["canon_work"]=runtime.graph.parents.canonical_batch_report();\n        report["root_recipe"]=')

    import os
    if os.getenv("EGGFUSE_BENCH_CANON_ROOTS_ONLY")=="yes":return
    import importlib.util
    spec=importlib.util.spec_from_file_location('canonical_frame_overlay',HERE/'frames.py')
    frames=importlib.util.module_from_spec(spec);spec.loader.exec_module(frames);frames.install(crate)

    import os
    sp=importlib.util.spec_from_file_location('canonical_subscriptions',HERE/'forward.py')
    forward=importlib.util.module_from_spec(sp);sp.loader.exec_module(forward);forward.metadata(crate)
    if os.getenv('EGGFUSE_BENCH_CANON_FORWARD')=='compact':forward.install(crate)
