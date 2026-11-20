"""Install immutable, prefix-local source proof receipts before learned suffix expansion."""

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace(s, old, new):
    if s.count(old) != 1:
        raise ValueError(f"unsupported source near {old[:70]}")
    return s.replace(old, new)


def install(crate):
    p = crate / "src/ordinary_witness.rs"
    s = replace(p.read_text(), "struct Store {", "struct Store {early:EarlyGuards,")
    s = replace(s, "let s=Store{", "let s=Store{early:EarlyGuards::default(),")
    s = replace(
        s,
        '"signature_stats":',
        '"transaction_guards":s.early.report(),"signature_stats":',
    )
    s = replace(
        s,
        "let (steps,slots)=s.compile_stack(&c)?;",
        """let (steps,slots)=s.compile_stack(&c)?;
            if s.early.mode!=GuardMode::Off && !s.early.prepare(&c,&steps,rid)? {return Ok(vec![])}""",
    )
    s = replace(
        s,
        "let issued=clock.map",
        """if s.early.mode!=GuardMode::Off && s.early.active.is_some(){
            s.early.stats[rid].raw+=s.counts.raw_tuples-initial.0;
        }
        let issued=clock.map""",
    )
    p.write_text(s + '\ninclude!("transaction_guards.rs");\n')
    shutil.copyfile(HERE / "guards.rs", crate / "src/transaction_guards.rs")
    p = crate / "src/ordinary_shortlist.rs"
    s = replace(
        p.read_text(),
        "            for &(col,slot) in &d.publish{",
        """            if self.early.active.is_some() && !self.early.permits(c,i,j,row)?{continue}
            for &(col,slot) in &d.publish{""",
    )
    p.write_text(s)
    p = crate / "examples/joint_witness_session.rs"
    marker = "        let initial_cells = runtime.graph.stats.cells_created;"
    p.write_text(
        replace(
            p.read_text(),
            marker,
            """        if let Some(m)=req["early_guards"].as_str(){ordinary_witness::configure_early_guards(&program,m)?;}
"""
            + marker,
        )
    )
