import shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent


def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src';p=src/'adaptive_verification.rs'
    s=change(p.read_text(),'struct VerifiedRows {','struct VerifiedRows {\n    projected: ProjectedChecks,')
    s=change(s,'        let mut registers = std::mem::take(&mut self.registers);','''        if self.projected.mode!=0 && let Some(Some(plan))=self.projected.plans.get(tok.rid){
            return self.verify_projected(g,r,tok,wm,work,plan.clone());
        }
        let mut registers = std::mem::take(&mut self.registers);''')
    p.write_text(s+'\ninclude!("projected_checks.rs");\n')
    shutil.copyfile(HERE/'projected.rs',src/'projected_checks.rs')
    p=src/'adaptive_rows.rs'
    s=change(p.read_text(),'"verification":self.verify.stats,','"projection":self.verify.projected.stats,"verification":self.verify.stats,')
    p.write_text(s)
    p=src/'runtime.rs'
    s=change(p.read_text(),'    pub fn single_report(&self)', '''    pub fn configure_projected_checks(&mut self,mode:u64)->Result<()>{
        let trial=self.stage_spine.single.as_mut().ok_or("projection verifier needs a neural proposer")?;
        trial.install_projected_checks(&self.graph.program,mode)
    }
    pub fn single_report(&self)''');p.write_text(s)
    p=crate/'examples/joint_witness_session.rs'
    marker='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),marker,'''        if let Some(mode)=req["projected_checks"].as_u64(){runtime.configure_projected_checks(mode)?;}
'''+marker))
