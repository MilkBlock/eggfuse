"""Add a frozen finite-domain code table to the isolated Rust research runtime."""
from pathlib import Path
import shutil


def replace(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError((path,old))
    path.write_text(text.replace(old,new))


def install(crate):
    src=Path(crate)/'src'
    here=Path(__file__).resolve().parent
    shutil.copyfile(here/'codes.rs',src/'baked_port_codes.rs')
    ordinary=src/'ordinary_witness.rs'
    replace(ordinary,'struct Store {','struct Store {empty_shortlist:Rc<Vec<usize>>,packed_lookup:bool,column_codes:bool,baked_codes:Option<BakedCodes>,')
    replace(ordinary,'let s=Store{','let s=Store{empty_shortlist:Rc::new(Vec::new()),packed_lookup:false,column_codes:false,baked_codes:None,')
    replace(ordinary,'    fn code(&mut self,v:&Value)->Port{','''    fn code(&mut self,v:&Value)->Port{
        if let Some(table)=&self.baked_codes{return table.port(v,self.views);}''')
    replace(ordinary,'struct Index {short:', 'struct Index {packed:Option<rustc_hash::FxHashMap<u32,Rc<Vec<usize>>>>,codes:Option<Vec<Port>>,short:')
    replace(ordinary,'for (i,row) in f.rows.iter().enumerate(){bins.entry(self.code(&row.values[col]).key).or_default().push(i);}','''let mut codes=self.column_codes.then(||Vec::with_capacity(f.rows.len()));
        let mut groups=rustc_hash::FxHashMap::<u32,Vec<usize>>::default();
        for (i,row) in f.rows.iter().enumerate(){
            let port=self.code(&row.values[col]);
            if self.packed_lookup{
                groups.entry(signature(port,false,self.views)).or_default().push(i);
            }else{
                bins.entry(port.key).or_default().push(i);
            }
            if let Some(ref mut column)=codes{column.push(port);}
        }''')
    replace(ordinary,'Index{short:ShortIndex::new','Index{packed:self.packed_lookup.then(||groups.into_iter().map(|(k,v)|(k,Rc::new(v))).collect()),codes,short:ShortIndex::new')
    replace(src/'ordinary_shortlist.rs','        self.memo_counts.calls+=1;','''        self.memo_counts.calls+=1;
        if let Some(groups)=&idx.packed{
            // For radius zero, the intersection of all view buckets is a direct
            // lookup of the concatenated signatures. Keep source order within the bucket.
            self.counts.score_bucket_reads+=1;self.memo_counts.header_probes+=1;
            return groups.get(&signature(q,true,self.views)).unwrap_or(&self.empty_shortlist).clone();
        }''')
    replace(src/'ordinary_shortlist.rs','let key=s.code(&frame.rows[i].values[col]);',
            'let key=idx.codes.as_ref().map_or_else(||s.code(&frame.rows[i].values[col]),|codes|codes[i]);')
    with ordinary.open('a') as f:f.write('\ninclude!("baked_port_codes.rs");\n')
    session=crate/'examples/joint_witness_session.rs'
    replace(session,'        let initial_cells = runtime.graph.stats.cells_created;', '''        if let Some(file)=req["baked_codes"].as_str(){
            ordinary_witness::use_baked_port_codes(&std::fs::read(file)?,req["baked_row_index"].as_bool().unwrap_or(false),req["packed_lookup"].as_bool().unwrap_or(false))?;
        }
        let initial_cells = runtime.graph.stats.cells_created;''')
    shutil.copyfile(here/'bake.rs',crate/'examples/bake_port_codes.rs')
