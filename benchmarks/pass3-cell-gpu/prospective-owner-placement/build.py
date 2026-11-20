"""Build natural, catalogue-directed placement in the pinned completed-owner store."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def splice(text, old, new):
    if text.count(old) != 1:
        raise ValueError(old)
    return text.replace(old, new)


def build(base, out):
    out.mkdir(parents=True, exist_ok=False)
    tree = out / "tree"
    subprocess.run(["cp", "-cR", base / "tree", tree], check=True)
    src = tree / "engine/cell-runtime/src"
    p = src / "shared_owner_transfer.rs"
    s = p.read_text()
    old = "    fn transfer_completed_storage<const POOL:bool>(&mut self,reuse_segments:bool,singletons:bool)->Result<usize> {"
    s = splice(s, old, old + """
        self.place_completed_storage::<POOL>(reuse_segments,singletons,0,&mut [0;5])
    }
    pub fn prospective_owner_charge(&self)->[usize;7] { self.cells.live_owner_charge() }
    pub fn place_completed_fragments(&mut self,mode:u8,counts:&mut [u64;5])->Result<usize> {
        self.place_completed_storage::<true>(false,true,mode,counts)
    }
    fn place_completed_storage<const POOL:bool>(&mut self,reuse_segments:bool,singletons:bool,
        mode:u8,counts:&mut [u64;5])->Result<usize> {""")
    before = "            if POOL && self.cells.completed_owner_has_external_sources(&ids) {"
    s = splice(s, before, """            if mode>0 && ids.len()==component.frames.len() {
                let plan=&self.program.cell_ownership.composition;
                let next=plan.transitions.partition_point(|(key,_)|key.shape<component.shape);
                let extendable=plan.transitions.get(next).is_some_and(|(key,_)|key.shape==component.shape);
                let existing=ids.iter().filter(|id|self.cells.completed_meta(**id).is_some()).count();
                if existing==0 && extendable {
                    // A complete ordinary component can receive a later member under the frozen catalog.
                    // Preserve its present boundary. Never subdivide the group at this point.
                    counts[0]+=1; counts[1]+=ids.len() as u64;
                    groups.push(ids);
                    continue;
                }
                if existing>0 && existing<ids.len() {
                    counts[2]+=1;
                    if mode==2 && !self.cells.completed_owner_has_external_sources(&ids) {
                        // Prefix backing allocations were published before this admission. Only the
                        // newly completed cohort gets storage; the prefix is neither moved nor cut.
                        ids.retain(|id|self.cells.completed_meta(*id).is_none());
                        counts[3]+=1; counts[4]+=ids.len() as u64;
                        groups.push(ids);
                        continue;
                    }
                }
            }
""" + before)
    p.write_text(s)
    driver = tree / "tools/cell-compiler/examples/existing_owner_transfer.rs"
    s = splice(driver.read_text(), "    let mut action = false;", """    let mut action = false;
    let placement=match a[3].as_str() {"pooled"=>0,"isolate"=>1,"defer"=>2,_=>return Err("unknown layout".into())};
    if !matches!(mode_arg(&a),"keep"|"merge"|"policy") {return Err("expected an unseeded action".into());}
    let mut placement_counts=[0u64;5];
    let mut owner_peak=[0;7];""".replace("mode_arg(&a)", "a[1].as_str()"))
    start = s.index('        if mode.starts_with("split") && seed.is_empty()')
    end = s.index('        e.graph.compact_source_record_capacity()',start)
    s = s[:start] + """        e.graph.place_completed_fragments(placement,&mut placement_counts)?;
        let charge=e.graph.prospective_owner_charge();
        for (peak,live) in owner_peak.iter_mut().zip(charge) { *peak=(*peak).max(live); }
""" + s[end:]
    s = splice(s,'"probe":probe,"source_checks"', '"placement":placement_counts,"owner_final":e.graph.prospective_owner_charge(),"owner_peak":owner_peak,"probe":probe,"source_checks"')
    driver.write_text(s)
    from census import install
    install(src,driver)
    env = dict(os.environ, CARGO_TARGET_DIR=str(out / "target"))
    subprocess.run(["cargo", "build", "--offline", "--locked", "--release", "-p", "eggfuse-cell-compiler",
                    "--features", "iterative-bake,sparse-cells,storage-metrics", "--example", "existing_owner_transfer"],
                   env=env, cwd=tree, check=True)
    shutil.copy2(out / "target/release/examples/existing_owner_transfer", out / "engine")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("base", "out"):
        cli.add_argument(key,type=Path)
    args=cli.parse_args()
    build(args.base,args.out)
