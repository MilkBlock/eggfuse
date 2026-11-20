from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(text,old,new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    path=src/'ordinary_witness.rs'
    s=change(path.read_text(),'struct Store {','struct Store {wake:Wake,')
    s=change(s,'let s=Store{','let s=Store{wake:Wake::default(),')
    s=change(s,'"bridges":s.bridges.work,','"wake":s.wake.stats,"bridges":s.bridges.work,')
    path.write_text(s+'\ninclude!("wake_roots.rs");\n')
    copyfile(HERE/'reverse.rs',src/'wake_roots.rs')
    path=src/'connected_requests.rs'
    s=change(path.read_text(),'        for (i, left) in src.frame.rows.iter().enumerate() {','''        let active=if self.wake.mode>0 {
            self.wake_roots(c,src,point,target,&key,join_col)
        }else{None};
        let n=active.as_ref().map_or(src.frame.rows.len(),Vec::len);
        for pos in 0..n {
            let (i,supplied)=active.as_ref().map_or((pos,None),|v|v[pos]);
            let left=&src.frame.rows[i];''')
    s=change(s,'            let receipt = if let Some(map) = &directory {','''            let receipt = if let Some(j)=supplied.filter(|_|self.wake.mode>=3) {
                let mid=&point.frame.rows[j];
                if self.detailed {
                    let expected=c.graph.lookup(point.table,&inputs)?.filter(|r|!r.hidden);
                    if expected.map(|r|r.witness)!=Some(mid.witness){return Err("stale woken function receipt".into())}
                    self.wake.stats.audited_receipts+=1;
                }
                self.wake.stats.direct_receipts+=1;
                let v=canon(mid.values.last().ok_or("empty function row")?,&c.graph.parents);
                Some((j,self.code(&v)))
            }else if let Some(map) = &directory {''')
    path.write_text(s)
    path=crate/'examples/joint_witness_session.rs'
    anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    path.write_text(change(path.read_text(),anchor,'''        if let Some(w)=req.get("wake_roots"){
            ordinary_witness::configure_wake(w.as_u64().ok_or("invalid activation mode")?)?;
        }
'''+anchor))
