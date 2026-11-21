from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    p=crate/'Cargo.toml';p.write_text(change(p.read_text(),'[features]','[features]\nreceipt-arena=[]\nreceipt-page16=[]\nreceipt-page64=[]'))
    src=crate/'src';p=src/'graph.rs';s=p.read_text()
    s=change(s,'#[cfg(feature = "sparse-cells")]\n#[path = "cell_arena.rs"]',
        '#[cfg(any(feature="sparse-cells",feature="receipt-arena"))]\n#[path = "cell_arena.rs"]')
    old='''    #[cfg(not(feature = "sparse-cells"))]
    pub cells: rustc_hash::FxHashMap<u32, Cell>,
    #[cfg(feature = "sparse-cells")]
    pub cells: arena::Cells,'''
    s=change(s,old,'''    #[cfg(not(any(feature="sparse-cells",feature="receipt-arena",feature="receipt-page16",feature="receipt-page64")))]
    pub cells: rustc_hash::FxHashMap<u32, Cell>,
    #[cfg(any(feature="sparse-cells",feature="receipt-arena"))]
    pub cells: arena::Cells,
    #[cfg(feature="receipt-page16")]
    pub cells: logical_pages::PackedCells<16>,
    #[cfg(feature="receipt-page64")]
    pub cells: logical_pages::PackedCells<64>,''')
    s+='''
#[cfg(any(feature="receipt-page16",feature="receipt-page64"))]
#[path="logical_cell_pages.rs"]
pub mod logical_pages;
impl Graph {
    pub fn receipt_store_report(&self)->serde_json::Value{
        #[cfg(any(feature="receipt-page16",feature="receipt-page64",feature="receipt-arena"))]
        {self.cells.placement_report()}
        #[cfg(not(any(feature="sparse-cells",feature="receipt-page16",feature="receipt-page64",feature="receipt-arena")))]
        {serde_json::json!({"layout":"hash","live":self.cells.len(),"record_capacity":self.cells.capacity()})}
        #[cfg(feature="sparse-cells")]
        {serde_json::json!({"layout":"sparse","live":self.cells.len()})}
    }
}
'''
    p.write_text(s);copyfile(HERE/'paged.rs',src/'logical_cell_pages.rs')
    p=src/'cell_arena.rs'
    with p.open('a') as f:f.write('''
#[cfg(feature="receipt-arena")]
impl Cells{pub fn placement_report(&self)->serde_json::Value{
    serde_json::json!({"layout":"arena","live":self.records.len(),"record_capacity":self.records.capacity(),"position_capacity":self.positions.capacity(),"outliers":self.outliers.len()})
}}
''')
    p=crate/'examples/joint_witness_session.rs';a='        let profile_work = req.get("cpu_profile").map'
    p.write_text(change(p.read_text(),a,'        report["physical_store"]=runtime.graph.receipt_store_report();\n'+a))
