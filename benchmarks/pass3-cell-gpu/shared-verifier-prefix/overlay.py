from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent

def change(src, old, new):
    if src.count(old) != 1:
        raise ValueError(old)
    return src.replace(old, new)

def install(crate):
    src = crate / 'src'
    path = src / 'adaptive_verification.rs'
    s = change(path.read_text(), 'struct VerifiedRows {', 'struct VerifiedRows {\n    family: FamilyChecks,')
    start = s.index('        if let Some(i) = p.pivot {', s.index('    fn verify('))
    loop = s.index('        for &i in &p.order {',start)
    end = s.index('        if r.seminaive && epoch < wm {',loop)
    prefix = s[start:end].replace('for &i in &p.order {','for &i in &p.order[..depth] {')
    # The independent miss path uses exactly the source verifier's pivot and step semantics.
    helper = '''
impl VerifiedRows {
    fn evaluate_prefix(&mut self,g:&Graph,r:&Rule,p:&Plan,tok:&Token,work:&mut[u64;8],
                       reg:&mut[Option<Value>], witnesses:&mut[Option<Dependency>], depth:usize)->Result<Option<u64>>{
        let mut epoch=0;
''' + prefix + '''        Ok(Some(epoch))
    }
}
'''
    s = s[:start] + '''        let mut completed=0;
        if let Some(layout)=self.family.layout.get(tok.rid).and_then(|v|v.clone()) {
            completed=layout.depth;
            let Some(e)=self.check_family(g,r,p,tok,work,reg,&mut witnesses,&layout)? else {return Ok(None)};
            epoch=e;
        } else ''' + s[start:loop].lstrip() + s[loop:].replace('        for &i in &p.order {','        for &i in &p.order[completed..] {',1)
    path.write_text(s+'\ninclude!("shared_verifier_prefix.rs");\n'+helper)
    copyfile(HERE/'family.rs',src/'shared_verifier_prefix.rs')
    p=src/'runtime.rs'
    anchor='    pub fn single_report(&self)'
    p.write_text(change(p.read_text(),anchor,'''    pub fn configure_shared_prefix(&mut self,mode:u64)->Result<()>{
        let trial=self.stage_spine.single.as_mut().ok_or("missing single-parent proposer")?;
        trial.install_family(&self.graph.program,mode)
    }
'''+anchor))
    p=src/'adaptive_rows.rs'
    p.write_text(change(p.read_text(),'"projection":self.verify.projected.stats,','"family":self.verify.family.stats,"projection":self.verify.projected.stats,'))
    p=crate/'examples/joint_witness_session.rs';anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),anchor,'''        if let Some(mode)=req["shared_prefix"].as_u64(){runtime.configure_shared_prefix(mode)?;}
'''+anchor))
