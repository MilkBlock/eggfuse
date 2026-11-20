"""Replace only reads of a table's maximum visible epoch in a sealed source plan."""
from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(old)
    return text.replace(old, new)


def install(crate):
    src = crate / "src"
    path = src / "ordinary_witness.rs"
    s = replace(path.read_text(), "struct Store {", "struct Store {watermarks:Watermarks,")
    s = replace(s, "let s=Store{", "let s=Store{watermarks:Watermarks::default(),")
    s = replace(s, '"counts":s.counts,', '"watermarks":s.watermarks.stats,"counts":s.counts,')
    old = "remaining[i]=remaining[i].max(s.frame(g,t)?.max_epoch);"
    new = """let max = if s.watermarks.mode >= 5 && (!rule.seminaive || remaining[i] >= mark) {
                    s.watermarks.stats.threshold_skips += 1;
                    remaining[i]
                } else if s.watermarks.mode >= 6 { s.threshold_epoch(g,t,mark)? }
                else if s.watermarks.mode == 0 { s.frame(g,t)?.max_epoch }
                else { s.source_max(g,t)? };
                remaining[i]=remaining[i].max(max);"""
    s = replace(s, old, new)
    anchor = "        let prepared=clock.map"
    s = replace(s, anchor, """        if matches!(s.watermarks.mode, 2 | 4..=7) && rule.seminaive && remaining[0] < mark {
            s.watermarks.stats.stale_rules += 1;
            return Ok(vec![]);
        }
""" + anchor)
    path.write_text(s+'\ninclude!("source_watermarks.rs");\n')
    copyfile(HERE / "frontier.rs", src / "source_watermarks.rs")
    path = crate / "examples/joint_witness_session.rs"
    anchor = "        let initial_cells = runtime.graph.stats.cells_created;"
    s = replace(path.read_text(), anchor, """        if let Some(v) = req.get("source_watermarks") {
            ordinary_witness::configure_watermarks(v.as_u64().ok_or("invalid source frontier policy")?)?;
        }
""" + anchor)
    path.write_text(s)
    path = src / "graph.rs"
    anchor = "    pub fn witness_count(&self, table: usize) -> usize {"
    method = """    pub(crate) fn current_member_epoch(&self, t:usize, d:Dependency) -> Option<u64> {
        let id = match (self.program.tables[t].virtual_fact, d) {
            (true, Dependency::Fact(f)) => f.ordered_id(),
            (false, Dependency::Function(i)) => i as u64,
            _ => return None,
        };
        #[cfg(not(feature="sparse-cells"))]
        let member = self.members[t].contains(&id);
        #[cfg(feature="sparse-cells")]
        let member = self.members[t].iter().any(|v| *v == id);
        if member { self.visible_epoch(d) } else { None }
    }
"""
    path.write_text(replace(path.read_text(), anchor, method + anchor))
