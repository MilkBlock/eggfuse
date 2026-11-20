"""Add matched storage-policy controls and live-payload checks to a detached historical source archive."""
import argparse
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent

def replace(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def prepare(root):
    f=root/'engine/cell-runtime/src/integral_storage.rs';s=f.read_text()
    s=replace(s,'pub(super) struct Store {','''pub(super) struct Store {
    trial_mode:u8,
    trial_allowed:Option<Vec<u32>>,
    trial_log:bool,
    trial_admissions:Vec<(u64,u32,u32,u32,u32,usize)>,''')
    marker='    pub fn physical_record_counts(&self) -> PhysicalRecords {'
    s=replace(s,marker,'''    pub fn configure_storage_trial(&mut self,mode:u8,allowed:Option<Vec<u32>>,log:bool){
        self.cells.integral.trial_mode=mode;self.cells.integral.trial_log=log;self.cells.integral.trial_allowed=allowed;
    }
    pub fn trial_admissions(&self)->&[(u64,u32,u32,u32,u32,usize)]{&self.cells.integral.trial_admissions}
    pub fn check_integral_trial_views(&self)->Result<(usize,usize,usize)>{
        let mut members=0;let mut multi=0;let mut facts=0;
        for (group,instance) in self.cells.integral.instances.iter().enumerate(){
            let mut first=None;let mut mixed=false;
            for (m,live) in instance.issued.iter().enumerate(){
                if live.id==ABSENT{continue;}members+=1;
                if let Some(epoch)=first{mixed|=epoch!=live.epoch}else{first=Some(live.epoch);}
                if self.cells.integral_address(live.id)!=Some(group*64+m) ||
                   self.cells.get(&live.id).is_some() || self.cells.completed_slots(live.id).is_some() ||
                   self.cells.completed_facts(live.id).is_some(){return Err("old source payload remained available".into());}
                let layout=&instance.layout.members[m];
                for op in 0..layout.ops{
                    let reference=FactRef{cell:live.id,op:op as u32};
                    if let Some(row)=self.row(Dependency::Fact(reference))?{
                        // A legacy physical fact address must still decode through the current member.
                        if row.witness!=Dependency::Fact(reference){return Err("member identity changed".into());}
                        facts+=1;
                    }
                }
            }
            multi+=mixed as usize;
        }
        Ok((members,multi,facts))
    }
'''+marker)
    f.write_text(s)
    f=root/'engine/cell-runtime/src/integral_storage_bake.rs';s=f.read_text()
    s=replace(s,'        let Dependency::Fact(root) = root else {\n            return None;\n        };','''        if matches!(self.cells.integral.trial_mode,1|2){return None;}
        let Dependency::Fact(root) = root else {
            return None;
        };''')
    marker='    pub(super) fn attach_integral_learned('
    s=replace(s,marker,'''    pub(super) fn attach_integral_learned(&mut self,root:FactRef,layout:Arc<Layout>,member:usize,id:u32,epoch:u64,depth:u32)->Result<bool>{
        let store=&self.cells.integral;
        if store.trial_allowed.as_ref().is_some_and(|mask|mask.binary_search(&id).is_err()){return Ok(false);}
        let base=layout.id;
        let dynamic=store.trial_mode==1;
        let accepted=dynamic || self.attach_integral_trial_inner(root,layout,member,id,epoch,depth)?;
        if accepted && self.cells.integral.trial_log{
            self.cells.integral.trial_admissions.push((epoch,id,root.cell,root.op,base,member));
        }
        Ok(accepted && !dynamic)
    }
    fn attach_integral_trial_inner(''')
    s=replace(s,'        } else if let Some(address) = self.cells.integral_address(root.cell) {','        } else if self.cells.integral.trial_mode!=2 && let Some(address) = self.cells.integral_address(root.cell) {')
    f.write_text(s)
    d=root/'tools/cell-compiler/examples';shutil.copy2(HERE/'storage_driver.rs',d/'online_storage_trial.rs')
    f=d/'runtime_storage_peak.rs';s=f.read_text();marker='    let setup_peak = PEAK.load(Relaxed);'
    s=replace(s,'    if !(args.len()>=3','''    let trial=if let Some(i)=args.iter().position(|x|x=="--matched-storage"){
        let mode=args.remove(i+1).parse::<u8>()?;let file=args.remove(i+1);args.remove(i);Some((mode,file))
    }else{None};
    if !(args.len()>=3''')
    s=replace(s,marker,'''    if let Some((mode,file))=trial{
        let allowed=serde_json::from_slice(&fs::read(file)?)?;
        e.graph.configure_storage_trial(mode,Some(allowed),false);
    }
'''+marker);f.write_text(s)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);prepare(p.parse_args().root)
