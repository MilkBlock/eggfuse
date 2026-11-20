"""Build the pre-action model gate into the existing checked owner transfer experiment."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
PREV = HERE.parent / "existing-owner-transfer"

def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old,new)

def build(a):
    a.out.mkdir(parents=True,exist_ok=False)
    tree=a.out/'tree'
    subprocess.run(['cp','-cR',a.base/'tree',tree],check=True)
    src=tree/'engine/cell-runtime/src'
    graph=(PREV/'graph.rs').read_text()
    graph=replace(graph,'impl Graph {',(HERE/'policy.rs').read_text()+'\nimpl Graph {')
    graph=replace(graph,'accounting: fn(bool)', 'policy: Option<&OwnerPolicy>, cut_index: usize, skip: &mut usize, accounting: fn(bool)')
    graph=replace(graph,'let cut = ids.len().div_ceil(2);','''if *skip > 0 { *skip -= 1; continue; }
                let cut = 1 + cut_index % (ids.len() - 1);''')
    graph=replace(graph,'let previous = mapping(self);','''let previous = mapping(self);
            let features = self.cells.owner_features(&ids,old[0].0);
            let score = policy.map(|p|p.score(&features)).transpose()?;
            let selected = score.map_or(mode.ends_with("merge"), |s|s>0.);
            // Seal the choice with the exact physical parents and generation before the transfer.
            let issued = json!({"epoch":self.epoch,"shape":shape,"members":previous,"features":features,
                "score":score,"compose":selected,"checkpoint":policy.map(|p|(&p.weights,p.intercept))});
            let issued_id = crate::checksum::artifact_digest(&issued);
            if previous != mapping(self) {return Err("owner generation changed at issue".into());}''')
    graph=replace(graph,'else if mode.ends_with("merge")','else if selected')
    graph=replace(graph,'"kind":"existing_pair"','"kind":"existing_pair","issuer":issued,"issuer_id":issued_id')
    (src/'old_pair_graph.rs').write_text(graph)
    store=(PREV/'store.rs').read_text()+'''
impl Cells {
    pub(crate) fn owner_features(&self, ids:&[u32], destination:usize)->[usize;8] {
        let mut features=[0;8];
        let mut stages=std::collections::BTreeSet::new();
        let mut layouts=std::collections::BTreeSet::new();
        for id in ids {
            let view=self.completed.frame_view(self.completed_index(*id).expect("verified member"));
            let side=usize::from(view.owner != destination);
            features[side]+=1;
            features[2+side]+=view.layout.slots.len();
            features[4+side]+=view.layout.ops.len();
            stages.insert(self.completed.stage(&view).epoch);
            layouts.insert(view.layout.template);
        }
        features[6]=stages.len(); features[7]=layouts.len(); features
    }
}
'''
    (src/'old_pair_store.rs').write_text(store)
    driver=(PREV/'driver.rs').read_text()
    driver=replace(driver,'    loop {','''    let weights=a.get(7).filter(|v|v.as_str()!="-").map(|path| -> Result<_,Box<dyn std::error::Error>> {
        Ok(serde_json::from_slice(&fs::read(path)?)?)
    }).transpose()?;
    let cut=a.get(5).map(|v|v.parse()).transpose()?.unwrap_or(0);
    let mut skip=a.get(6).map(|v|v.parse()).transpose()?.unwrap_or(0);
    loop {''')
    driver=replace(driver,'&seed, accounting','&seed, weights.as_ref(), cut, &mut skip, accounting')
    driver=replace(driver,'if action && mode.ends_with("-probe") {','''if action && a.get(8).is_some_and(|v|v=="capture") {break;}
            if action && mode.ends_with("-probe") {''')
    (tree/'tools/cell-compiler/examples/existing_owner_transfer.rs').write_text(driver)
    env=dict(os.environ,CARGO_TARGET_DIR=str(a.out/'target'))
    subprocess.run(['cargo','build','--offline','--locked','--release','-p','eggfuse-cell-compiler','--features','iterative-bake,sparse-cells,storage-metrics','--example','existing_owner_transfer'],cwd=tree,env=env,check=True)
    shutil.copy2(a.out/'target/release/examples/existing_owner_transfer',a.out/'engine')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('base','out'):p.add_argument(n,type=Path)
    build(p.parse_args())
