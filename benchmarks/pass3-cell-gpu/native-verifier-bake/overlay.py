from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    path=src/'projected_checks.rs'
    s=change(path.read_text(),'struct ProjectedStats {','struct ProjectedStats {\n    installed_native:usize, native_calls:u64,')
    s=change(s,'struct ProjectedRule {','struct ProjectedRule {\n    native:Option<NativeVerifier>,')
    s=change(s,'if !(1..=2).contains(&mode)','if !(1..=4).contains(&mode)')
    s=change(s,'                Some(std::rc::Rc::new(ProjectedRule {','''                let native=if mode>=3 {
                    VerifierShape::lower(&query).and_then(|sh|native_entry(&format!("{sh:?}")))
                        .filter(|(_,n)|mode==4 || *n>=2).map(|(f,_)|f)
                }else{None};
                Some(std::rc::Rc::new(ProjectedRule {native,''')
    s=change(s,'        s.stats.programs = s.plans', '        s.stats.installed_native=s.plans.iter().flatten().filter(|p|p.native.is_some()).count();\n        s.stats.programs = s.plans')
    pos='        let mut receipts = smallvec::SmallVec::<[(usize, Dependency); 8]>::new();'
    s=change(s,pos,'''        if let Some(f)=compiled.native {
            self.projected.stats.native_calls+=1;
            return f(self,g,r,&compiled,&row,wm,work);
        }
'''+pos)
    path.write_text(s+'\ninclude!("verifier_codegen.rs");\ninclude!("baked_verifiers.rs");\n')
    copyfile(HERE/'codegen.rs',src/'verifier_codegen.rs')
    (src/'baked_verifiers.rs').write_text('fn native_entry(_: &str)->Option<(NativeVerifier,usize)>{None}\n')
    p=src/'lib.rs'
    p.write_text(change(p.read_text(),'mod single_witness;','mod single_witness;\npub use single_witness::emit_verifier_library;'))
    p=crate/'examples/joint_witness_session.rs'
    anchor='    let args: Vec<_> = std::env::args_os().skip(1).collect();'
    p.write_text(change(p.read_text(),anchor,anchor+'''
    if let [flag,input,source,metadata]=args.as_slice() && flag=="--emit-verifiers" {
        let program=Program::parse(serde_json::from_slice(&std::fs::read(input)?)?)?;
        let (code,shapes)=eggfuse_cell_runtime::emit_verifier_library(&program);
        std::fs::write(source,code)?;
        std::fs::write(metadata,serde_json::to_vec_pretty(&shapes)?)?;
        return Ok(());
    }'''))
