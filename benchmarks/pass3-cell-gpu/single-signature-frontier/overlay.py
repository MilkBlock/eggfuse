import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"unsupported insertion near {old[:80]}")
    return text.replace(old, new)


def install(crate):
    src = crate / "src"
    p = src / "ordinary_witness.rs"
    s = p.read_text()
    s = change(s, "struct Store {", "struct Store {single_epochs:SingleEpochs,")
    s = change(s, "let s=Store{", "let s=Store{single_epochs:SingleEpochs::default(),")
    s = change(
        s,
        '"signature_stats":',
        '"single_epochs":s.single_epochs.report(),"signature_stats":',
    )
    s = change(
        s, "struct Frame {table:usize,", "struct Frame {born_at_union:u64, table:usize,"
    )
    s = change(
        s,
        "Frame{table:t,generation:version,rows,max_epoch}",
        "Frame{born_at_union:g.stats.unions,table:t,generation:version,rows,max_epoch}",
    )
    p.write_text(s + '\ninclude!("single_epochs.rs");\n')
    p = src / "incremental_raw.rs"
    s = p.read_text()
    s = change(
        s,
        "let frame = Rc::new(Frame {",
        "let frame = Rc::new(Frame {born_at_union:graph.stats.unions,",
    )
    anchor = "self.pair_stats.high_directories += 1;"
    s = change(
        s,
        anchor,
        "self.single_epochs.native_marks.insert(key,(frame.generation,frame.born_at_union));\n"
        + anchor,
    )
    p.write_text(s)
    p = src / "adaptive_rows.rs"
    s = p.read_text()
    s = change(s, "struct SourceHeader {", "pub(crate) struct SourceHeader {")
    s = change(
        s,
        "    source: Option<Dependency>,\n    version:",
        "    pub(crate) source: Option<Dependency>,\n    pub(crate) version:",
    )
    s = change(
        s, "struct RowEngine {", "struct RowEngine {\n    signature_budget: bool,"
    )
    s = change(
        s,
        "        self.rows.prefilter =",
        '        self.rows.signature_budget = spec["signature_frontier"].as_bool().unwrap_or(false);\n        self.rows.prefilter =',
    )
    s = change(
        s,
        "        let n = sources.len();",
        """        let guarded;
        let sources = if self.rows.signature_budget && !can_prefilter && p.pivot.is_some() && r.seminaive && wm!=0 {
            let live=p.order.iter().filter_map(|i|match r.query[*i].call {Call::Table(t)=>Some(self.rows.verify.frontier(g,t)>=wm),_=>None}).collect::<Vec<_>>();
            guarded = crate::ordinary_witness::single_epoch_filter(g,rid,p.pivot.unwrap(),&p.order,&live,wm,sources)?;
            guarded.as_deref().unwrap_or(sources)
        } else {sources};
        let n = sources.len();""",
    )
    p.write_text(s)
    p = crate / "examples/joint_witness_session.rs"
    s = p.read_text()
    marker = "        let initial_cells = runtime.graph.stats.cells_created;"
    p.write_text(
        change(
            s,
            marker,
            """        if let Some(m)=req["signature_frontier"].as_object(){ordinary_witness::configure_single_epochs(m)?;}
"""
            + marker,
        )
    )
    shutil.copyfile(HERE / "frontier.rs", src / "single_epochs.rs")
