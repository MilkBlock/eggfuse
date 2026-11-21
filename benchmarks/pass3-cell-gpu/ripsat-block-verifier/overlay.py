"""Carry verified admission through actual internal returns on the frozen issuing head."""
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
edit = run_path(str(HERE.parent / "ripsat-set-receipt/overlay.py"))["edit"]


def install(crate):
    src = crate / "src"
    strict = src / "strict_named.rs"
    pub = src / "ripsat_set_publication.rs"
    edit(strict, "struct Permit {", "struct Permit {block:bool,")
    edit(strict, "struct Owner {", "struct Owner {block:bool,")
    edit(strict, "struct State {", "struct State {block_enabled:bool,")
    edit(strict, "s.actor=Actor::parse", """s.block_enabled=spec["block_verifier"]==true;
    if s.block_enabled && s.set_plan.is_none(){return Err("block requires checked Set plan".into())}
    s.actor=Actor::parse""")
    edit(strict, "immediate_serial:serial,prior: vec![]", """block:s.block_enabled && code & (1usize<<31)!=0,
                immediate_serial:serial,prior: vec![]""")
    edit(strict, "assert!(s.known.insert(serial));", """assert!(s.known.insert(serial));
            if s.block_enabled && code & (1usize<<31)!=0 {s.set_counts.admissions+=1;}""")
    edit(strict, "immediate_serial:serial,prior: internal.path", "block:internal.block,immediate_serial:serial,prior: internal.path")
    edit(strict, "let owner = Owner {set_data:None,", """let owner = Owner {
                block:a.block && s.set_plan.as_ref().is_some_and(|plan|path.as_slice()==[plan.first]),
                set_data:None,""")
    edit(pub, "        let o = Owner {", "        let o = Owner {block:record.block,")
    edit(pub, "struct PublishedSet {", "struct PublishedSet {\n    block: bool,")
    edit(pub, "struct PublicationCounts {", """struct PublicationCounts {
    admissions: u64,
    block_captures: u64,
    replayed_operands: u64,
    capture_row_reads: u64,
    capture_ns: u64,""")
    # set_attempt is immediately upstream of the actual canonical lookup. Its
    # successful fresh branch alone has the authority to capture the real operands.
    edit(pub, "        let c=g.cells.get", """        let start=s.receipt_index.work.profile.then(std::time::Instant::now);
        let block=a.block;
        if !block {
        let c=g.cells.get""")
    edit(pub, "        let mut rederived=", "        s.set_counts.replayed_operands+=1;\n        let mut rederived=")
    edit(pub, "        let mut fields=fields;", """        }
        let mut fields=fields;""")
    edit(pub, "        let w=Dependency::Fact(f);let row=", """        if !block || s.set_fault=="wrong_fields" {
        s.set_counts.capture_row_reads+=1;
        let w=Dependency::Fact(f);let row=""")
    edit(pub, "        let path=vec![p.first,p.second];", """        }
        if block {s.set_counts.block_captures+=1;}
        let path=vec![p.first,p.second];""")
    edit(pub, "Some(PublishedSet{fact:f", "Some(PublishedSet{block,fact:f")
    edit(pub, "fields,path,trail});Ok(())", """fields,path,trail});
        if let Some(start)=start {s.set_counts.capture_ns+=start.elapsed().as_nanos() as u64;}
        Ok(())""")
    # Raw equality implies equal canonical values. Unequal fields may still
    # be equivalent after union, so retain that check at the Run boundary.
    edit(strict, "any(|(a,b)|crate::value::canon(a,&g.parents)!=",
         "any(|(a,b)|(!o.block || a!=b) && crate::value::canon(a,&g.parents)!=")
    edit(pub, "    block_captures: u64,", "    block_captures: u64,\n    direct_binds: u64,\n    internal_bind_ns: u64,")
    edit(strict, "pub(crate) fn link(serial: u64, root: u64, rid: usize, w: Dependency) -> Result<()>", """
// Only link can mint this after matching a previously released block owner.
pub(crate) struct BlockPort { pub(super) serial:u64, pub(super) rid:usize,
    pub(super) witness:Dependency, pub(super) version:u64, _sealed:() }
pub(crate) fn bind_clock()->Option<std::time::Instant>{
    S.with_borrow(|v|v.as_ref().is_some_and(|s|s.receipt_index.work.profile))
        .then(std::time::Instant::now)
}
pub(crate) fn bind_elapsed(start:std::time::Instant){
    let ns=start.elapsed().as_nanos() as u64;
    S.with_borrow_mut(|v|v.as_mut().unwrap().set_counts.internal_bind_ns+=ns);
}
pub(crate) fn link(serial: u64, root: u64, rid: usize, w: Dependency) -> Result<Option<BlockPort>>""")
    edit(strict, "        assert!(s.issued.insert(serial, owner).is_none());", """        let grant=owner.block.then(||BlockPort{serial,rid,witness:w,version:owner.version,_sealed:()});
        s.set_counts.direct_binds+=u64::from(grant.is_some());
        assert!(s.issued.insert(serial, owner).is_none());""")
    edit(strict, "s.stats.actual_internal += 1;\n        Ok(())", "s.stats.actual_internal += 1;\n        Ok(grant)")
    single = src / "single_witness.rs"
    edit(single, "                crate::strict_named::link(", "                let grant=crate::strict_named::link(")
    start = "                let receipt=crate::joint_root::internal_point"
    end = '?.ok_or("internal root projection failed")?;'
    content = single.read_text()
    original = content[content.index(start):content.index(end, content.index(start)) + len(end)]
    edit(single, original, """                let start=crate::strict_named::bind_clock();
                let root_recipe=if let Some(grant)=grant {
                    if closed.pivot!=0 || lane.refs.as_slice()!=[(0,lane.w)] || grant.version!=lane.version {
                        return Err("changed internal block port".into());
                    }
                    crate::joint_root::bind_block(grant,g.epoch,&lane.values)?
                } else {
""" + original.replace("let root_recipe=", "").removesuffix(";") + """
                };
                if let Some(start)=start {crate::strict_named::bind_elapsed(start);}
""")
    with (src / "joint_root.rs").open("a") as out:
        out.write((HERE / "bind.rs").read_text())
    # begin is before the receiving RHS. Only its successful return settles
    # this finite program; a live input alone cannot confirm completion.
    edit(strict, "struct State {block_enabled:", "struct State {terminal_block:bool,block_enabled:")
    edit(strict, "s.active = None;\n        s.physical = None;", "s.active = None;\n        s.terminal_block=false;\n        s.physical = None;")
    edit(strict, "                s.set_counts.confirmed+=1;", """                s.terminal_block=internal.block;
                s.set_counts.confirmed+=1;""")
    edit(pub, "    admissions: u64,", "    admissions: u64,\n    completed_blocks:u64,")
    edit(pub, "        let Some(record) = s.pending_set.take()", """        if std::mem::take(&mut s.terminal_block) && success {s.set_counts.completed_blocks+=1;}
        let Some(record) = s.pending_set.take()""")
    # Finishing the last instruction is insufficient to claim exhaustion. The
    # only re-entry for this family is a fresh pivot; also observe nested
    # constructor births here, before output's ordinary physical-frame filter.
    edit(strict, "struct State {terminal_block:", "struct State {fresh_pivot:bool,terminal_block:")
    edit(strict, "s.terminal_block=false;", "s.terminal_block=false;\n        s.fresh_pivot=false;")
    edit(strict, "        if s.physical != Some(f.cell) {", """        if s.terminal_block {
            let plan=s.set_plan.as_ref().expect("admitted terminal has checked plan");
            s.fresh_pivot |= t==plan.table || s.child_table.get(&plan.first[2])==Some(&t);
        }
        if s.physical != Some(f.cell) {""")
    edit(pub, "    completed_blocks:u64,", "    completed_blocks:u64,\n    exhausted_fresh_ports:u64,")
    edit(pub, "&& success {s.set_counts.completed_blocks+=1;}", """&& success {
            s.set_counts.completed_blocks+=1;
            s.set_counts.exhausted_fresh_ports+=u64::from(!s.fresh_pivot);
        }""")
