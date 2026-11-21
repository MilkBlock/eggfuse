"""Pass surviving scalar point witnesses to the native verifier in packed per-rule pages."""
from pathlib import Path

def edit(path,a,b):
    s=path.read_text()
    if s.count(a)!=1:raise ValueError(a)
    path.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';cert=src/'scalar_certificates.rs';row=src/'adaptive_rows.rs'
    single=src/'single_witness.rs';verify=src/'adaptive_verification.rs'
    edit(cert,'    pivot_table: usize,','    mapping:Vec<usize>,\n    pivot_table: usize,')
    edit(cert,'        let mut points = Vec::new();','        let mut mapping=vec![usize::MAX;rule.query.len()];\n        let mut points = Vec::new();')
    edit(cert,'            if !points.contains(&(table, col)) {','''            mapping[i]=points.iter().position(|&x|x==(table,col)).unwrap_or(points.len());
            if !points.contains(&(table, col)) {''')
    edit(cert,'            pivot_table,','            mapping,\n            pivot_table,')
    edit(cert,'    enabled: bool,','    positive:bool, fault:bool, pages:Vec<PointPage>,\n    enabled: bool,')
    edit(cert,'    examined: u64,','    attached:u64, sealed_points:u64, peak_capacity_bytes:usize,\n    examined: u64,')
    edit(cert,'h: &SourceHeader, wm: u64','h: &SourceHeader, wm: u64, serial:u64')
    edit(cert,'        let mut greatest = row.epoch;','''        let mut greatest = row.epoch;
        let mut receipts=smallvec::SmallVec::<[ScalarRef;2]>::new();''')
    edit(cert,'            let Some(epoch) = g.single_scalar_epoch(t, key)? else {','''            let epoch=if self.positive{
                g.single_scalar_handle(t,key)?.map(|(dep,version)|{receipts.push(ScalarRef{dep,version});version})
            }else{g.single_scalar_epoch(t,key)?};
            let Some(epoch) = epoch else {''')
    edit(cert,'        Ok(false)\n    }\n}', '''        if self.positive{
            if self.fault{for r in &mut receipts{r.version^=1;}}
            let page=&mut self.pages[rid];
            page.push(serial,&receipts);
            counts.attached+=1;counts.sealed_points+=receipts.len() as u64;
            counts.peak_capacity_bytes=counts.peak_capacity_bytes.max(page.serials.capacity()*8+page.points.capacity()*std::mem::size_of::<ScalarRef>());
        }
        Ok(false)
    }
}''')
    with cert.open('a') as f:f.write((Path(__file__).parent/'handoff.rs').read_text())
    edit(row,'self.rows.scalar.enabled=spec["scalar_certificates"]==true;','''self.rows.scalar.enabled=spec["scalar_certificates"]==true;
        self.rows.scalar.positive=spec["scalar_handoff"]==true;
        self.rows.scalar.fault=spec["fault_scalar_epoch"]==true;
        if self.rows.scalar.positive && (!self.rows.scalar.enabled || self.rows.verify.mode!=2 || !self.rows.batch){
            return Err("scalar handoff needs the exact scalar compiler and batched register verifier".into())
        }''')
    edit(row,'self.rows.scalar.counts.resize_with(self.plans.len(),Default::default);','''self.rows.scalar.counts.resize_with(self.plans.len(),Default::default);
            if self.rows.scalar.positive{self.rows.scalar.pages.resize_with(self.plans.len(),Default::default);}''')
    edit(row,'self.rows.scalar.rejects(g,rid,h,wm)?','self.rows.scalar.rejects(g,rid,h,wm,self.serial)?')
    edit(row,'"scalar_certificates":self.scalar.counts,','"scalar_certificates":self.scalar.counts,"point_transfers":[self.verify.transferred,self.verify.checked_transfers],')
    edit(single,'self.rows.verify.check(g,r,&p,&token,wm,&mut self.work)?','''{
                let ports=self.rows.scalar.lane(rid,token.id)?;
                self.rows.verify.check(g,r,&p,&token,wm,&mut self.work,ports)?}''')
    edit(single,'        Ok(answers)','''        if self.rows.scalar.positive{self.rows.scalar.pages[rid].finish()?;}
        Ok(answers)''')
    edit(verify,'struct VerifiedRows {','struct VerifiedRows {\n    transferred:u64, checked_transfers:u64,')
    edit(verify,'        work: &mut [u64; 8],\n    ) -> Result<Option<Instance>> {','''        work: &mut [u64; 8],
        ports:Option<PointLane<'_>>,
    ) -> Result<Option<Instance>> {
        if ports.is_some() && (self.memo_enabled || self.projected.mode!=0){return Err("unexpected scalar verifier specialization".into())}''')
    edit(verify,'work, registers.as_mut_slice())','work, registers.as_mut_slice(),ports)')
    edit(verify,'        reg: &mut [Option<Value>],','        reg: &mut [Option<Value>],\n        ports:Option<PointLane<\'_>>,')
    edit(verify,'                    let Some(row) = self.point(g, *table, values)?.filter(|r| !r.hidden) else {','''                    let result=if let Some(lane)=&ports {
                        let receipt=lane.points.get(lane.mapping[i]).ok_or("missing compiled scalar port")?;
                        let row=g.row(receipt.dep)?.ok_or("retired scalar port")?;
                        if row.hidden || row.witness!=receipt.dep || row.table!=*table || row.epoch!=receipt.version ||
                           row.values.len()!=2 || values.len()!=1 || !g.single_scalar_key_equal(&row.values[0],&values[0]){
                            return Err("invalid scalar point witness".into());
                        }
                        if lane.audit{
                            let truth=g.lookup(*table,&values)?.ok_or("transferred scalar point missing exact source")?;
                            if truth.witness!=row.witness || truth.epoch!=row.epoch || truth.values!=row.values || truth.hidden{
                                return Err("transferred scalar point disagrees with exact lookup".into());
                            }
                            self.checked_transfers+=1;
                        }
                        self.transferred+=1;Some(row)
                    }else{self.point(g,*table,values)?};
                    let Some(row) = result.filter(|r| !r.hidden) else {''')
    graph=src/'graph.rs'
    with graph.open('a') as f:f.write('''
impl Graph {
    pub(crate) fn single_scalar_key_equal(&self,a:&Value,b:&Value)->bool{
        crate::value::canon(a,&self.parents)==crate::value::canon(b,&self.parents)
    }
    pub(crate) fn single_scalar_handle(&self,t:usize,value:&Value)->Result<Option<(Dependency,u64)>>{
        let key=[crate::value::canon(value,&self.parents)];
        if self.port_keys_enabled(t){
            return Ok(self.lookup_canonical(t,&key)?.filter(|r|!r.hidden).map(|r|(r.witness,r.epoch)));
        }
        Ok(self.function_index(t,&key).and_then(|i|self.functions.get(i).filter(|f|f.live).map(|f|(Dependency::Function(i),f.epoch))))
    }
}
''')
