"""Allow authenticated speculative Cell records to become the ordinary graph's backing."""
from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    copyfile(HERE/'resident.rs',src/'resident_cell_pages.rs')
    p=src/'graph.rs'
    s=change(p.read_text(),'pub struct Graph {','#[path="resident_cell_pages.rs"]\npub mod resident;\npub struct Graph {')
    s=change(s,'pub cells: rustc_hash::FxHashMap<u32, Cell>,','pub cells: resident::NativeCells,')
    a=s.index('    fn store_cell(&mut self, id: u32, cell: Cell) {')
    b=s.index('    pub fn frame(',a)
    body=s[a:b]
    assert body.count('self.cells.insert(id, cell);')==1
    common=body.replace('fn store_cell(&mut self, id: u32, cell: Cell)','fn account_cell(&mut self, id:u32, template:usize,parent:Option<FactRef>)').replace('if let Some(parent) = cell.parent','if let Some(parent) = parent').replace('id,cell.template,','id,template,').replace('        self.cells.insert(id, cell);\n','')
    s=s[:a]+common+'''    fn store_cell(&mut self,id:u32,cell:Cell){
        self.account_cell(id,cell.template,cell.parent);
        self.cells.insert(id,cell);
    }
    pub fn resident_slab_report(&self)->J{self.cells.report()}
'''+s[b:]
    s=change(s,'''if let Some(mut staged)=self.take_private(template){
            let (values,parent)=self.stage_inputs(template,values,parent);
            staged.frame.values=values;staged.frame.parent=parent;
            self.store_cell(id,staged.frame);self.check_private(id,staged.early_ptr,staged.preconstructed,true);''','''if let Some(staged)=self.take_private(template){
            let (values,parent)=self.stage_inputs(template,values,parent);
            self.publish_claim(id,staged,true,|c|{c.values=values;c.parent=parent;});''')
    p.write_text(s)
    p=src/'speculative_staging.rs';s=p.read_text()
    s=change(s,'pub(crate) struct Claimed {\n    pub frame: Cell,','enum Backing{Owned(Cell), Resident(usize)}\npub(crate) struct Claimed {\n    backing:Backing,')
    s=change(s,'pub(crate) struct Staging {','pub(crate) struct Staging {\n    resident_width:usize, pending_resident:Vec<Box<[resident::Lane]>>,')
    s=change(s,'        Ok(Self {\n            timing,','''        let resident_width=if cfg["resident_headers"].as_bool()==Some(true){
            if !matches!(timing,Timing::Run) || storage!=Storage::Group{return Err("resident slabs need Run-wide authenticated group vouchers".into())}
            let w=cfg["page_width"].as_u64().unwrap_or(64);
            if !matches!(w,16|64|256){return Err("resident page width must be 16, 64 or 256".into())}
            w as usize
        }else{0};
        Ok(Self {
            resident_width,pending_resident:vec![],timing,''')
    a='        let mut slab = Vec::with_capacity(count);'
    s=change(s,a,'''        if self.resident_width!=0 {
            assert!(self.pending_resident.is_empty());
            let mut templates=grants.iter().flat_map(|&(rid,n)|std::iter::repeat_n(g.program.rules[rid].template,n));
            let mut left=count;
            while left>0 {
                let size=left.min(self.resident_width);
                let mut lanes:Box<[_]>=templates.by_ref().take(size).map(|t|{
                    let facts=g.program.templates[t].ops.len().clamp(1,4);
                    let c=Cell::private_layout(t,self.epoch,facts);
                    let bytes=c.facts.stage_bytes();
                    self.bytes+=bytes;self.stats.private_payload_capacity_bytes+=bytes;
                    resident::Lane::private(c)
                }).collect::<Vec<_>>().into_boxed_slice();
                for lane in lanes.iter_mut(){lane.freeze();}
                self.pending_resident.push(lanes);left-=size;
            }
            let headers=count*size_of::<resident::Lane>();
            self.stats.preconstructed+=count;self.stats.slabs+=self.pending_resident.len();
            self.stats.header_capacity_bytes+=headers;self.bytes+=headers;
            self.stats.peak_private_bytes=self.stats.peak_private_bytes.max(self.bytes);
            self.used_budget+=count;self.stats.granted+=count;
            self.stats.peak_slots=self.stats.peak_slots.max(self.used_budget);
            return 0;
        }
'''+a)
    a='            let i=r.span.start+r.span.taken;r.span.taken+=1;'
    s=change(s,a,a+'''
            if self.resident_width!=0{
                self.stats.used+=1;self.seen+=1;
                return Some(Claimed{backing:Backing::Resident(i),early_ptr:0,preconstructed:true})
            }''')
    s=change(s,'        Some(Claimed {\n            frame,','        Some(Claimed {\n            backing:Backing::Owned(frame),')
    a=s.index('    pub(crate) fn spec_run(&self,');b=s.index('    pub(crate) fn spec_winner(',a)
    s=s[:a]+'''    pub(crate) fn spec_run(&mut self,set:&str,rules:&[usize]){
        if let Some(s)=&self.spec_cells{
            let mut st=s.borrow_mut();st.start(self,set,rules);
            if st.resident_width!=0{
                self.cells.start(self.epoch,st.resident_width,std::mem::take(&mut st.pending_resident),st.audit);
            }
        }
    }
    pub(crate) fn spec_end_run(&mut self){
        if let Some(s)=&self.spec_cells{s.borrow_mut().finish();}
        self.cells.finish();
    }
'''+s[b:]
    a=s.index('    pub(crate) fn publish_private_temp(');b=s.index('\n    }',a)
    original=s[a:b+6]
    left=original.index('            c.parent = scratch.parent;');right=original.index('            self.store_cell(id, claimed.frame)')
    moves=original[left:right]
    s=s[:a]+'''    pub(super) fn publish_claim(&mut self,id:u32,claim:Claimed,direct:bool,init:impl FnOnce(&mut Cell)){
        let early=match claim.backing{
            Backing::Owned(mut c)=>{init(&mut c);self.store_cell(id,c);claim.early_ptr}
            Backing::Resident(i)=>{
                let (template,parent)={
                    let c=self.cells.private_mut(i);
                    init(c);(c.template,c.parent)
                };
                self.account_cell(id,template,parent);
                self.cells.publish(id,i)
            }
        };
        self.check_private(id,early,claim.preconstructed,direct);
    }
    pub(crate) fn publish_private_temp(&mut self,id:u32,mut scratch:Cell){
        if let Some(claim)=self.take_private(scratch.template){
            self.publish_claim(id,claim,false,|c|{
'''+moves+'''            });
        }else{self.store_cell(id,scratch);}
    }'''+s[b+6:]
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';a='        report["spec_cells"]=runtime.graph.spec_cells_report();'
    s=change(p.read_text(),a,a+'\n        report["resident_slabs"]=runtime.graph.resident_slab_report();')
    p.write_text(s)
