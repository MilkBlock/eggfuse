"""Instrument the existing integral issuer exactly at its public Run and inference boundaries."""
from pathlib import Path
from runpy import run_path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
rss=HERE.parent/"verified-wave-rss"
common=run_path(str(rss/"overlay.py"))
change=common["change"]


def install(crate):
    src=crate/"src"
    p=src/"rss_window.rs"
    p.write_text((rss/"window.rs").read_text()+"""
pub(crate) fn publish_run(n:u64,values:[u64;4]){
    // Seqlock: the observer also compares every sampled tuple with its audited Run ledger.
    put(8,n*2-1);put(4,n);put(5,values[0]);put(6,values[1]);put(9,values[2]);put(10,values[3]);put(8,n*2);
}
""")
    copyfile(HERE/"counters.rs",src/"yield_window.rs")
    p=src/"lib.rs";p.write_text(p.read_text()+'\npub mod rss_window;\npub mod yield_window;\n')
    p=src/"joint_root.rs";p.write_text(p.read_text()+'''
pub(crate) fn external_wire_counters()->[u64;3]{
    STATE.with_borrow(|c|c.as_ref().map_or([0;3],|s|[s.wire_bytes,s.emitted[0],s.emitted[1]]))
}
''')
    p=src/"integral_packets.rs";p.write_text(p.read_text()+'''
pub(crate) fn confirmed_total()->u64{S.with_borrow(|c|c.as_ref().map_or(0,|s|s.counts.confirmed as u64))}
''')
    p=src/"speculative_staging.rs";anchor='    pub(crate) fn spec_end_run(&self) {'
    p.write_text(change(p.read_text(),anchor,anchor+'\n        crate::yield_window::complete_run();'))
    p=crate/'examples/joint_witness_session.rs'
    a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),a,'''        eggfuse_cell_runtime::yield_window::configure(req["rss_file"].is_string(),req["rss_ledger"]==true);
'''+a))
    common["driver"](p,'req','eggfuse_cell_runtime::rss_window')
    a='        report["pre_post_ms"]='
    p.write_text(change(p.read_text(),a,'''        report["rss_runs"]=eggfuse_cell_runtime::yield_window::report();
'''+a))
