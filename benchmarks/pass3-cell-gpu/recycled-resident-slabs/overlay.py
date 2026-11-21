"""Add optional dense-page reuse to the audited nonmoving native slab store."""
from pathlib import Path
from shutil import copyfile

HERE = Path(__file__).resolve().parent


def replace(s, old, new):
    if s.count(old) != 1:
        raise ValueError(old)
    return s.replace(old, new)


def install(crate):
    src = crate / "src"
    copyfile(HERE / "recycle.rs", src / "recycle_cell_pages.rs")
    store = src / "resident_cell_pages.rs"
    s = store.read_text() + '\ninclude!("recycle_cell_pages.rs");\n'
    s = replace(s, "struct NativeCells {", """struct NativeCells {
    recycling: bool,
    reused_prefix: usize,
    grant_lanes: Vec<usize>,
    recycle: RecycleCosts,""")
    s = replace(s, "        for lanes in pages {", """        self.recycling = false;
        self.recycle.empty_runs += usize::from(pages.is_empty());
        self.recycle.new_pages += pages.len();
        for lanes in pages {
            self.recycle.fresh_header_slots += lanes.len();""")
    s = replace(s, "        (self.current[index / self.width], index % self.width)", """        if self.recycling {
            let loc = self.grant_lanes[index];
            return (loc >> 8, loc & 255);
        }
        (self.current[index / self.width], index % self.width)""")
    s = replace(s, "        self.stats.published += 1;", """        self.stats.published += 1;
        if self.recycling && index < self.reused_prefix { self.recycle.published_from_old_holes += 1; }""")
    assert s.count("page.epoch != self.epoch") == 2
    s = s.replace("page.epoch != self.epoch", "if self.recycling {c.started_epoch != self.epoch} else {page.epoch != self.epoch}")
    s = replace(s, '"old_run_reads":self.old_run_reads.get()', '''"old_run_reads":self.old_run_reads.get(),
            "recycle": self.recycle,"grant_lanes_capacity_bytes":self.grant_lanes.capacity()*size_of::<usize>()''')
    store.write_text(s)
    staging = src / "speculative_staging.rs"
    s = staging.read_text()
    s = replace(s, "    resident_width:usize,", "    recycle:bool, pending_layouts:Vec<(usize,usize,usize)>, resident_width:usize,")
    s = replace(s, "        Ok(Self {\n            resident_width,", """        let recycle=match cfg["recycle"].as_str(){None|Some("off")=>false,Some("dense") if resident_width!=0=>true,_=>return Err("recycle requires dense policy on resident Run slabs".into())};
        Ok(Self {
            recycle,pending_layouts:Vec::new(),resident_width,""")
    s = replace(s, "        if self.resident_width!=0 {", """        if self.recycle {
            assert!(self.pending_layouts.is_empty());
            self.pending_layouts.extend(grants.iter().filter(|(_,n)| *n>0).map(|&(rid,n)|{
                let t=g.program.rules[rid].template; (t,g.program.templates[t].ops.len().clamp(1,4),n)
            }));
            self.stats.preconstructed+=count; self.used_budget+=count; self.stats.granted+=count;
            self.stats.peak_slots=self.stats.peak_slots.max(self.used_budget);
            return 0;
        }
        if self.resident_width!=0 {""")
    s = replace(s, "            if st.resident_width!=0{", """            if st.recycle{
                let layouts=std::mem::take(&mut st.pending_layouts);
                let total=layouts.iter().map(|x|x.2).sum();
                let epoch=self.epoch; let mut payload_bytes=0;
                let cells=layouts.into_iter().flat_map(|(t,f,n)|std::iter::repeat_n((t,f),n)).map(|(t,f)|{
                    let c=Cell::private_layout(t,epoch,f); payload_bytes+=c.facts.stage_bytes(); c
                });
                let (fresh,pages)=self.cells.start_reused(epoch,st.resident_width,total,cells,st.audit);
                let header_bytes=fresh*size_of::<resident::Lane>();
                st.bytes+=payload_bytes+header_bytes;
                st.stats.slabs+=pages; st.stats.header_capacity_bytes+=header_bytes;
                st.stats.private_payload_capacity_bytes+=payload_bytes;
                st.stats.peak_private_bytes=st.stats.peak_private_bytes.max(st.bytes);
            }else if st.resident_width!=0{""")
    staging.write_text(s)
