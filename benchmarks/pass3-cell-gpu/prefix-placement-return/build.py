"""Install one first-placement gate in the checked completed-owner runtime."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(tree):
    src=tree/'engine/cell-runtime/src/shared_owner_transfer.rs'
    s=src.read_text()
    anchor='    fn place_completed_storage<const POOL:bool>(&mut self,reuse_segments:bool,singletons:bool,'
    prefix="""    // Return the stable source's current backing ID and its full occupancy.
    pub fn prefix_backings(&self,ids:&[u32])->Vec<Option<(usize,usize)>>{
        ids.iter().map(|&i|self.cells.physical_owner(i)).collect()
    }
    pub fn prefix_source_ports(&self,ids:&[u32])->Vec<(u32,u32)>{
        let mut out=Vec::new();
        for &i in ids {for op in self.cells.owner_ops(i){out.push((i,op))}}
        out.sort_unstable();out
    }
    pub fn prefix_port_values(&self,ports:&[(u32,u32)])->Result<serde_json::Value>{
        let mut rows=Vec::new();
        for &(cell,op) in ports {
            let row=self.row(Dependency::Fact(FactRef{cell,op}))?;
            rows.push(row.map(|r|(r.table,r.epoch,r.hidden,r.values.as_ref().to_vec())));
        }
        Ok(serde_json::json!(rows))
    }
    pub fn place_with_prefix_gate(&mut self,separate_arrivals:bool,gate:&mut dyn FnMut(usize,&[u32],[usize;8])->bool,counts:&mut [u64;5])->Result<usize>{
        self.place_completed_gate::<true>(false,true,if separate_arrivals {5} else {6},counts,gate)
    }
"""
    s=change(s,anchor,prefix+anchor)
    a=s.index(anchor);b=s.index('        if self.active_rhs',a)
    s=s[:b]+"""        self.place_completed_gate::<POOL>(reuse_segments,singletons,mode,counts,&mut |_,_,_|false)
    }
    fn place_completed_gate<const POOL:bool>(&mut self,reuse_segments:bool,singletons:bool,
        mode:u8,counts:&mut [u64;5],gate:&mut dyn FnMut(usize,&[u32],[usize;8])->bool)->Result<usize> {
"""+s[b:]
    anchor='                if existing==0 && extendable && mode!=3 && (mode!=4 || ids.len()>1) {'
    s=change(s,anchor,"""                let selected=if existing==0 && extendable && matches!(mode,5|6) && ids.len()<=16 {
                    let successors=plan.transitions[next..].partition_point(|(key,_)|key.shape==component.shape);
                    let mut slots=0;let mut facts=0;let mut readers=0;let mut templates=std::collections::BTreeSet::new();
                    for i in &ids {
                        let c=self.cells.get(i).expect("ordinary prefix at its first storage admission");
                        slots+=c.values.len();facts+=c.facts.len();templates.insert(c.template);
                        readers+=self.parent_users.get(i).copied().unwrap_or_default() as usize;
                    }
                    gate(component.shape,&ids,[ids.len(),slots,facts,pending.len(),bytes,successors,templates.len(),readers])
                } else {false};
                if existing==0 && extendable && (selected || (!matches!(mode,5|6) && mode!=3 && (mode!=4 || ids.len()>1))) {""")
    # Mode 6 keeps the source store's original extension behavior: an exclusive
    # prefix can absorb a later arriving child without another learned action.
    s=change(s,'if mode>=2 && !self.cells.completed_owner_has_external_sources(&ids) {',
             'if mode>=2 && mode!=6 && !self.cells.completed_owner_has_external_sources(&ids) {')
    src.write_text(s)
    p=tree/'tools/cell-compiler/examples/existing_owner_transfer.rs'
    s=change(p.read_text(),'    if a[1] == "bench" {',(HERE/'lean.rs').read_text()+(HERE/'gate.rs').read_text()+'\n    if a[1] == "bench" {' )
    helper,sep,_=(HERE.parent/'placement-lifetime/life.rs').read_text().partition('fn main() -> Outcome<()> {')
    if not sep:raise ValueError('missing graph probe helper boundary')
    main='fn main() -> Result<(), Box<dyn std::error::Error>> {'
    p.write_text(change(s,main,helper+main))



def manifest(base,out):
    touched=['engine/cell-runtime/src/shared_owner_transfer.rs','tools/cell-compiler/examples/existing_owner_transfer.rs']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    data=dict(input={k:sha(base/'tree'/k) for k in touched+['Cargo.lock']},
              output={k:sha(out/'tree'/k) for k in touched},engine=sha(out/'engine'),
              diagnostic=sha(HERE.parent/'placement-lifetime/life.rs'))
    (out/'build.json').write_text(json.dumps(data,indent=1)+'\n')


def build(base,out):
    out.mkdir(parents=True,exist_ok=False)
    tree=out/'tree'
    subprocess.run(['cp','-cR',base/'tree',tree],check=True)
    install(tree)
    subprocess.run(['cargo','build','--offline','--locked','--release','-p','eggfuse-cell-compiler','--features',
                    'iterative-bake,sparse-cells,storage-metrics','--example','existing_owner_transfer'],
                   cwd=tree,env=dict(os.environ,CARGO_TARGET_DIR=str(out/'target')),check=True)
    shutil.copy2(out/'target/release/examples/existing_owner_transfer',out/'engine')
    manifest(base,out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','out'):p.add_argument(name,type=Path)
    a=p.parse_args();build(a.base,a.out)
