from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def rep(source,a,b):
    if source.count(a)!=1:raise ValueError(a)
    return source.replace(a,b)
def install(crate):
    src=crate/'src';p=src/'strict_named.rs';s=p.read_text()
    s=rep(s,'struct State {','struct State {\n    receipt_index:ReceiptIndex,')
    s=rep(s,'let mut s = State {','let mut s = State {receipt_index:ReceiptIndex::parse(spec)?,')
    s=rep(s,'            s.stats.named_ports += 1;','            s.receipt_index.add(rid,w,epoch);\n            s.stats.named_ports += 1;')
    sig='pub(crate) fn open(g: &Graph, rid: usize, wm: u64) -> Result<Option<Vec<(Dependency, u64)>>> {'
    s=rep(s,sig,sig+'''
    let start=S.with_borrow(|v| v.as_ref().is_some_and(|s|s.receipt_index.work.profile)).then(std::time::Instant::now);
    let result=open_receipts(g,rid,wm);
    if let Some(t)=start{S.with_borrow_mut(|v|if let Some(s)=v {s.receipt_index.work.receiver_ns+=t.elapsed().as_nanos() as u64;});}
    result
}
fn open_receipts(g: &Graph,rid:usize,wm:u64)->Result<Option<Vec<(Dependency,u64)>>> {''')
    begin=s.index('        for (&w, o) in ports {',s.index('fn open_receipts'))
    stop=s.index('        if (!s.partial',begin)
    body=s[begin:stop].split(' in ports {\n',1)[1].rsplit('        }\n',1)[0]
    body=rep(body,'            s.stats.explicit_addresses += 1;','''            s.receipt_index.work.visited+=1;
            if s.receipt_index.mode==1 && o.version<wm {
                s.receipt_index.work.excluded_by_version+=1;continue;
            }
            s.receipt_index.work.member_checks+=u64::from(o.born<s.run);
            s.stats.explicit_addresses += 1;''')
    body=rep(body,'            let Some(row) = g.row(w)?','            s.receipt_index.work.row_reads+=1;\n            let Some(row) = g.row(w)?')
    # Preserve stable physical-address order without allocating in the original scan.
    s=s[:begin]+'''        s.receipt_index.work.release_calls+=1;
        s.receipt_index.work.possible+=ports.len() as u64;
        macro_rules! inspect_receipt { ($w:ident,$o:ident)=>{ {
            let w=$w;let o=$o;
'''+body+'''        } } }
        if s.receipt_index.mode==2 {
            let addresses=s.receipt_index.fresh(rid,wm);
            s.receipt_index.work.excluded_by_version+=(ports.len()-addresses.len()) as u64;
            for w in addresses{
                let o=ports.get(&w).ok_or("version posting lacks its signed owner")?;
                if o.version<wm{return Err("version posting is stale".into());}
                inspect_receipt!(w,o);
            }
        } else {
            for (&w,o) in ports {inspect_receipt!(w,o);}
        }
'''+s[stop:]
    s=rep(s,'"set_publication":s.set_counts,','"receipt_scan":s.receipt_index.work,"set_publication":s.set_counts,')
    p.write_text(s+'\ninclude!("receipt_index.rs");\n')
    p=src/'ripsat_set_publication.rs';s=p.read_text()
    a='        s.routes.entry(record.path).or_default()[0] += 1;'
    p.write_text(rep(s,a,'        s.receipt_index.add(p.second[2],w,record.generation);\n'+a))
    copyfile(HERE/'index.rs',src/'receipt_index.rs')

    higher=src/"higher_cell.rs"
    if higher.is_file():
        s=higher.read_text()
        start='                if s.ports'
        # The fresh reply was moved into the stable specialized owner above.
        hook='''                let generation=z.specialized[&h.root].result.as_ref().ok_or("absent specialized publication")?.generation;
                s.receipt_index.add(plan.second[2],w,generation);
'''
        higher.write_text(rep(s,start,hook+start))
