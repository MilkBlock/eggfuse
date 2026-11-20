use crate::{graph::{Dependency,Graph},program::{Arg,Call,Program,Result},precomputed_forest::Packet,slots::Slots,value::Value};
use serde_json::{json,Value as J};
use std::{collections::{BTreeMap,BTreeSet},ffi::{c_void,CString},ptr::NonNull,time::Instant};

unsafe extern "C"{
    fn ef_delta_open(src:*const i8,catalog:*const i32,claims:u32,ports:u32,rules:u32,width:i32)->*mut c_void;
    fn ef_delta_bank(ctx:*mut c_void,index:i32)->*mut i32;
    fn ef_delta_run(ctx:*mut c_void,seconds:*mut f64)->i32;
    fn ef_delta_close(ctx:*mut c_void);
}
pub(crate) struct Sidecar{
    handle:NonNull<c_void>,mode:String,width:usize,claims:usize,rule_count:usize,
    ports:Vec<(usize,usize)>,claim_ports:Vec<Option<usize>>,active_rules:BTreeSet<usize>,by_rule:BTreeMap<usize,Vec<(usize,usize)>>,
    last:Vec<Vec<i32>>,sources:Vec<Option<Dependency>>,versions:Vec<i32>,done:BTreeSet<usize>,
    symbols:BTreeMap<Value,i32>,values:Vec<Value>,identities:BTreeMap<Dependency,i32>,
    latest:u64,dispatched:bool,scans:u64,changes:u64,bytes:u64,schedule_bytes:u64,ack_bytes:u64,
    launches:u64,service_reads:u64,delivered:u64,reply_bytes:u64,publication_s:f64,exchange_s:f64,gpu_s:f64,
}
impl Drop for Sidecar{fn drop(&mut self){unsafe{ef_delta_close(self.handle.as_ptr());}}}
impl Sidecar{
    pub(crate) fn open(program:&Program,packet:&Packet,mode:String)->Result<Self>{
        if !["delta","snapshot","wrong-port","ready"].contains(&mode.as_str()){return Err("invalid port replica mode".into());}
        let width=program.tables.iter().map(|t|t.schema.len()).max().unwrap_or(1).max(1);
        let n=packet.catalog.len();let mut catalog=vec![-1i32;n*(11+width)];let mut ports=Vec::new();
        let mut known=BTreeMap::new();let mut by_rule=BTreeMap::<usize,Vec<(usize,usize)>>::new();let mut claim_ports=vec![None;n];let mut active=BTreeSet::new();
        for (id,(slot,token)) in packet.catalog.iter().zip(&packet.children).enumerate(){
            if token[0]==0 || token[5]<0{continue;}
            if token[5]!=1{return Err("delta comparison requires the same universal one-atom certificate".into());}
            let [origin,port,rid,pivot]=*slot;let parent=*packet.roots.get(origin).ok_or("unknown root token")?;
            let r=program.rules.get(rid).ok_or("unknown child")?;let a=r.query.get(pivot).ok_or("bad pivot")?;
            let Call::Table(table)=a.call else{return Err("invalid published parent table".into())};
            if r.query.len()!=1 || r.inputs.len()>width{return Err("unproved universal width".into());}
            let pos=*known.entry((parent,port)).or_insert_with(||{ports.push((parent,port));ports.len()-1});
            active.insert(rid);claim_ports[id]=Some(pos);by_rule.entry(rid).or_default().push((id,pos));
            let desc=&mut catalog[id*(11+width)..(id+1)*(11+width)];
            // Required source port/schema plus the actual sealed envelope to be verified by Metal.
            desc[..11].copy_from_slice(&[pos as i32,parent as i32,port as i32,rid as i32,pivot as i32,table as i32,
                packet.roots.get(token[1] as usize).copied().map_or(-1,|r|r as i32),token[2] as i32,token[3] as i32,token[4] as i32,r.inputs.len() as i32]);
            for (j,s) in r.inputs.iter().enumerate(){
                desc[11+j]=a.args.iter().position(|v|matches!(v,Arg::Slot(i) if i==s)).ok_or("unbound projection")? as i32;
            }
        }
        let src=CString::new(include_str!("sidecar.metal")).unwrap();
        let handle=NonNull::new(unsafe{ef_delta_open(src.as_ptr(),catalog.as_ptr(),n as u32,ports.len() as u32,program.rules.len() as u32,width as i32)})
            .ok_or("failed to initialize persistent Metal port verifier")?;
        let np=ports.len();Ok(Self{handle,mode,width,claims:n,rule_count:program.rules.len(),ports,claim_ports,active_rules:active,by_rule,
            last:vec![vec![0;8+width];np],sources:vec![None;np],versions:vec![0;np],done:BTreeSet::new(),
            symbols:BTreeMap::new(),values:Vec::new(),identities:BTreeMap::new(),latest:0,dispatched:false,scans:0,changes:0,
            bytes:0,schedule_bytes:0,ack_bytes:0,launches:0,service_reads:0,delivered:0,reply_bytes:0,
            publication_s:0.,exchange_s:0.,gpu_s:0.})
    }
    pub(crate) fn epoch<F>(&mut self,g:&Graph,rules:&[usize],wm:&[u64],published:&BTreeMap<(usize,usize),Dependency>,
                           used:&BTreeSet<usize>,current:F)->Result<()>
        where F:Fn(Dependency)->Option<(usize,usize)>{
        self.latest=g.epoch;self.dispatched=false;
        let start=Instant::now();let w=8+self.width;
        let mut scheduled_ports=BTreeSet::new();
        if self.mode=="ready"{
            for rid in rules{if let Some(ids)=self.by_rule.get(rid){
                for &(id,port) in ids{if !used.contains(&id){scheduled_ports.insert(port);}}
            }}
            if !scheduled_ports.iter().any(|&p|published.contains_key(&self.ports[p]) || self.sources[p].is_some()){
                self.publication_s+=start.elapsed().as_secs_f64();return Ok(());
            }
        }
        let bank=unsafe{std::slice::from_raw_parts_mut(ef_delta_bank(self.handle.as_ptr(),1),w*self.ports.len())};
        let mut record=vec![0;w];let mut any=false;
        let poll:Box<dyn Iterator<Item=usize>>=if self.mode=="ready"{
            Box::new(scheduled_ports.into_iter())
        }else{Box::new(0..self.ports.len())};
        for index in poll{
            let port=&self.ports[index];self.scans+=1;record.fill(0);let dep=published.get(port).copied();
            if let Some(dep)=dep && let Some(row)=g.row(dep)?{
                any=true;
                let next=self.identities.len()+1;let identity=*self.identities.entry(dep).or_insert(next as i32);
                let publisher=current(dep);
                record[0]=identity;record[2]=publisher.map_or(-1,|p|p.0 as i32);record[3]=publisher.map_or(-1,|p|p.1 as i32);
                if self.mode=="wrong-port"{record[3]=-1;}
                record[4]=row.table as i32;record[5]=i32::try_from(row.epoch).map_err(|_|"epoch overflow")?;
                record[6]=i32::from(row.hidden);record[7]=row.values.len() as i32;
                for (j,v) in row.values.iter().enumerate(){
                    let id=if let Some(id)=self.symbols.get(v){*id}else{
                        let id=i32::try_from(self.values.len()+1).map_err(|_|"symbol bank overflow")?;
                        self.values.push(v.clone());self.symbols.insert(v.clone(),id);id
                    };record[8+j]=id;
                }
            }
            record[1]=self.versions[index];let changed=self.last[index]!=record;
            if changed{
                self.versions[index]+=1;record[1]=self.versions[index];self.last[index].copy_from_slice(&record);self.changes+=1;
            }
            if changed || self.mode=="snapshot"{bank[index*w..(index+1)*w].copy_from_slice(&record);self.bytes+=(w*4) as u64;}
            self.sources[index]=dep;
        }
        let ack=unsafe{std::slice::from_raw_parts_mut(ef_delta_bank(self.handle.as_ptr(),3),self.claims)};
        for &id in used.difference(&self.done){ack[id]=1;self.ack_bytes+=4;}
        if used.len()!=self.done.len(){self.done=used.clone();}
        self.publication_s+=start.elapsed().as_secs_f64();
        if !any||!rules.iter().any(|r|self.active_rules.contains(r)){return Ok(());}
        let start=Instant::now();let sched=unsafe{std::slice::from_raw_parts_mut(ef_delta_bank(self.handle.as_ptr(),2),self.rule_count)};
        sched.fill(-1);for &id in rules{sched[id]=i32::try_from(wm[id]).map_err(|_|"watermark overflow")?;}
        self.schedule_bytes+=(4*self.rule_count) as u64;
        let mut elapsed=0.;if unsafe{ef_delta_run(self.handle.as_ptr(),&mut elapsed)}!=1{return Err("GPU dynamic verifier failed".into());}
        self.launches+=1;self.dispatched=true;self.gpu_s+=elapsed;self.exchange_s+=start.elapsed().as_secs_f64();Ok(())
    }
    pub(crate) fn take(&mut self,id:usize,dep:Dependency,rid:usize,g:&Graph)->Result<Option<Slots>>{
        self.service_reads+=1;
        if !self.dispatched || self.latest!=g.epoch{return Ok(None);}
        let Some(port)=self.claim_ports[id] else{return Ok(None)};
        let w=4+self.width;let out=unsafe{std::slice::from_raw_parts(ef_delta_bank(self.handle.as_ptr(),4).add(w*id),w)};
        self.reply_bytes+=4;
        if out[0]!=1{return Ok(None);}
        if self.sources[port]!=Some(dep)||self.identities.get(&dep)!=Some(&out[1])||self.versions[port]!=out[2]{return Ok(None);}
        let inputs=&g.program.rules[rid].inputs;
        if out[3] as usize!=inputs.len(){return Err("GPU returned wrong projected arity".into());}
        let mut slots=Slots::default();
        for (j,&s) in inputs.iter().enumerate(){
            let value=usize::try_from(out[4+j]).ok().and_then(|i|i.checked_sub(1)).and_then(|i|self.values.get(i))
                .ok_or("GPU returned uninterned value")?;
            slots.insert(s,value.clone());
        }
        self.reply_bytes+=((3+inputs.len())*4) as u64;self.delivered+=1;Ok(Some(slots))
    }
    pub(crate) fn report(&self)->J{json!({"mode":self.mode,"port_slots":self.ports.len(),"source_scans":self.scans,
        "changed_port_records":self.changes,"state_write_bytes":self.bytes,"schedule_bytes":self.schedule_bytes,"ack_bytes":self.ack_bytes,
        "launches":self.launches,"device_projected_replies_delivered":self.delivered,"source_cursor_requests":self.service_reads,
        "reply_bytes":self.reply_bytes,"publication_ms":self.publication_s*1000.,"exchange_ms":self.exchange_s*1000.,
        "metal_ms":self.gpu_s*1000.,"interned_runtime_values":self.values.len()})}
}
