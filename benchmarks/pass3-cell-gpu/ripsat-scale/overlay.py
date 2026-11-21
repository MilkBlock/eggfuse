from pathlib import Path
from shutil import copyfile


def edit(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f"{path}: expected exactly one {old!r}")
    path.write_text(source.replace(old, new))


def install(crate):
    src = crate / "src"
    copyfile(Path(__file__).with_name("fragment.rs"), src / "rhs_fragment.rs")
    with (src / "lib.rs").open("a") as out:
        out.write("\npub mod rhs_fragment;\n")
    session = crate / "examples/joint_witness_session.rs"
    anchor = 'eggfuse_cell_runtime::strict_named::configure(&req["strict_named"],&runtime.graph)?;'
    edit(session, anchor, anchor + '\n        eggfuse_cell_runtime::rhs_fragment::configure(&req["rhs_fragments"],&runtime.graph,&digest,audit)?;')
    anchor = 'report["strict_named"]=eggfuse_cell_runtime::strict_named::report();'
    edit(session, anchor, anchor + '\n        report["rhs_fragments"]=eggfuse_cell_runtime::rhs_fragment::report();\n        if audit {report["rhs_fragment_writes"]=eggfuse_cell_runtime::rhs_fragment::writes();}')
    for filename, count in [("adaptive_root_page.rs", "inputs.len()"), ("multi_root_pages.rs", "count")]:
        anchor = f"let template=crate::strict_named::tag(rid,template,{count});"
        edit(src / filename, anchor, anchor + f"\n        let template=crate::rhs_fragment::issue(rid,template,{count});")
    joint = src / "joint_root.rs"
    edit(joint, "recipe.template!=rule.template", "crate::rhs_fragment::source(rid,recipe.template)!=Some(rule.template)")
    edit(joint, "let Some(state)=s.as_mut()else{return Ok(source_template)};",
         "crate::rhs_fragment::activate(rid,0,0);let Some(state)=s.as_mut()else{return Ok(source_template)};")
    edit(joint, "r.template!=source_template", "crate::rhs_fragment::source(rid,r.template)!=Some(source_template)")
    anchor = "crate::strict_named::begin(r.serial,rid,!r.refs.is_empty(),r.strict_code)?;"
    edit(joint, anchor, anchor + "\n        crate::rhs_fragment::activate(rid,r.template,r.serial);")
    edit(joint, "r.serial,rid,r.template));", "r.serial,rid,source_template));")
    edit(joint, "r.serial,rid,r.template,epoch,r.refs", "r.serial,rid,source_template,epoch,r.refs")
    edit(joint, "Ok(r.template)", "Ok(source_template)")
    # Common constructor/receipt implementation, after any proven elision or
    # history transfer. All other effects stay at their original source ordinal.
    runtime = src / "runtime.rs"
    anchor = "for (i, op) in ops.iter().enumerate().skip(first_op) {"
    edit(runtime, anchor, "let fragment=crate::rhs_fragment::current();\n        "+anchor)
    anchor = "if !(crate::cell::RhsFrame { cell, receipts: &mut effect_receipts })"
    edit(runtime, anchor, """if let Some(block)=&fragment && let Some(ins)=block.ops.get(&i) {
                let mut frame=crate::cell::RhsFrame{cell,receipts:&mut effect_receipts};
                frame.fragment_construct(&mut self.graph,i,ins)?;
                block.applied(i);
                completed_prefix=i+1;
                continue;
            }
            """+anchor)
    anchor="impl RhsFrame<'_> {"
    edit(src/"cell_eval.rs",anchor,anchor+"""
    pub(crate) fn fragment_construct(&mut self,g:&mut Graph,op:usize,ins:&crate::rhs_fragment::Instruction)->Result<()> {
        self.construct(g,op,ins.table,&ins.args,ins.dst)
    }
""")
