"""Add optional sparse/cached generation to the installed native provider without modifying its source tree."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
def swap(s,a,b):
    if s.count(a)!=1:raise ValueError(f'incompatible ordinary provider: {a!r}')
    return s.replace(a,b)

def install(crate):
    src=Path(crate)/'src'
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=swap(s,'struct Store {views:', 'struct Store {hint_fault:u8,flat:Vec<(Dependency,u32)>,flat_offsets:Vec<u32>,issued_generations:Vec<u64>,accel:u8,memo_counts:MemoStats,neighbors:Vec<Vec<(usize,u64)>>,views:')
    s=swap(s,'    let seal=mode.starts_with("seal");','''    let (hint_fault,mode)=if let Some(s)=mode.strip_prefix("badpos"){(1,s)}else if let Some(s)=mode.strip_prefix("badgen"){(2,s)}else{(0,mode)};
    let (accel,mode)=if let Some(s)=mode.strip_prefix("sparse"){(1,s)}else if let Some(s)=mode.strip_prefix("epoch"){(2,s)}else if let Some(s)=mode.strip_prefix("memo"){(3,s)}else if let Some(s)=mode.strip_prefix("stack"){(4,s)}else if let Some(s)=mode.strip_prefix("flat"){(5,s)}else{(0,mode)};
    let seal=mode.starts_with("seal");''')
    s=swap(s,'    let s=Store{views,','''    if accel>0 && (!seal || !matches!(mode,"learned"|"adaptive"|"certified")){
        return Err("shortlist overlay requires a sealed trained policy".into())
    }
    let s=Store{hint_fault,flat:vec![],flat_offsets:vec![],issued_generations:vec![],accel,memo_counts:MemoStats::default(),neighbors:if accel>0{neighborhoods(radius)}else{vec![]},views,''')
    s=swap(s,'json!({"generator":s.mode,','json!({"shortlist":s.memo_counts,"accel":s.accel,"hint_fault":s.hint_fault,"generator":s.mode,')
    s=swap(s,'struct Index {generation:u64,','struct Index {short:ShortIndex,generation:u64,')
    s=swap(s,'let h=Rc::new(Index{generation:f.generation,bins});','''if self.accel>0{
            if let Some(old)=self.indexes.get(&(t,col)).cloned(){self.evict_memo(&old.short.saved.borrow());}
            else{self.memo_counts.indexes+=1}
            self.memo_counts.rebuilds+=1;
        }
        let h=Rc::new(Index{short:ShortIndex::new(&bins),generation:f.generation,bins});''')
    s=swap(s,'!required.iter().all(|(col,q)|','!required.iter().skip(usize::from(this.accel>0)).all(|(col,q)|')
    s=swap(s,'            if matches!(self.mode.as_str(),"adaptive"|"certified"){','''            if self.accel>0{
                let selected=self.shortlist(&frame,&idx,col,q);
                for &j in selected.iter(){visit(self,&frame.rows[j])?}
            }else if matches!(self.mode.as_str(),"adaptive"|"certified"){''')
    s=swap(s,'s.descend(&c,0,p.clone(),&mut out,&mut raw)?;','''if s.accel>=4{
            let (steps,slots)=s.compile_stack(&c)?;
            s.issued_generations.clear();
            if s.accel>=5{s.issued_generations.extend(steps.iter().map(|d|d.frame.generation));}
            s.emit_stack(&c,&steps,0,0,&mut vec![],&mut vec![None;slots],&mut raw)?;
        }else{s.descend(&c,0,p.clone(),&mut out,&mut raw)?;}''')
    s=swap(s,'            let mut no_more=vec![];','''            if s.accel>=5{
                s.counts.peak_rule_tuples=s.counts.peak_rule_tuples.max(s.flat.len()/c.pick_count);
                s.memo_counts.peak_flat_bytes=s.memo_counts.peak_flat_bytes.max(s.flat.capacity()*std::mem::size_of::<(Dependency,u32)>());
                s.verify_flat(&c,&p,&mut out)?;
            }
            let mut no_more=vec![];''')
    s=s.replace('self.publish_ports(&atom.args,&row.values,&mut p);','if self.accel<5{self.publish_ports(&atom.args,&row.values,&mut p);}')
    s=s.replace('self.publish_ports(&atom.args[atom.args.len()-1..],std::slice::from_ref(&v),&mut p);','if self.accel<5{self.publish_ports(&atom.args[atom.args.len()-1..],std::slice::from_ref(&v),&mut p);}')
    p.write_text(s+'\ninclude!("ordinary_shortlist.rs");\n')
    shutil.copyfile(HERE/'shortlist.rs',src/'ordinary_shortlist.rs')
