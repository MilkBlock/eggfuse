from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src';p=src/'graph.rs'
    s=rep(p.read_text(),'pub struct Graph {','pub struct Graph {\n    pub(crate) request_unions:Option<std::collections::VecDeque<u64>>,')
    s=rep(s,'        let mut g = Self {','        let mut g = Self {request_unions:None,')
    p.write_text(rep(s,'        self.stats.unions += 1;','''        if let Some(ids)=&mut self.request_unions {
            if ids.len()==16384 {ids.pop_front();}ids.push_back(hi);
        }
        self.stats.unions += 1;'''))
    p=src/'ordinary_witness.rs';s=rep(p.read_text(),'struct Store {','struct Store {patch_ports:PatchPorts,')
    s=rep(s,'let s=Store{','let s=Store{patch_ports:PatchPorts::default(),')
    s=rep(s,'"wake":s.wake.stats,','"patch_ports":s.patch_ports.work,"wake":s.wake.stats,')
    old='            if let Some(frame)=self.update_frame(g,t,version)?{return Ok(frame);}'
    s=rep(s,old,'''            let patch=if self.patch_ports.mode>=2 && self.patch_ports.versions.keys().any(|(table,_)|*table==t) {
                self.frames.get(&t).zip(self.frame_changes.get(&t)).filter(|(_,p)|p.generation==version)
                    .map(|(f,p)|(f.generation,p.changed.iter().copied().collect::<Vec<_>>()))
            }else{None};
            if let Some(frame)=self.update_frame(g,t,version)?{
                if let Some((old,delta))=patch {self.patch_ports.transition(t,old,version,&delta);}
                return Ok(frame)
            }''')
    p.write_text(s+'\ninclude!("request_subscription.rs");\n');copyfile(HERE/'ports.rs',src/'request_subscription.rs')
    p=src/'wake_roots.rs';s=p.read_text().replace('self.wake_index(c, point, 1)?','self.current_ports(c, point, 1)?').replace('self.wake_index(c, src, *scol)?','self.current_ports(c, src, *scol)?')
    s=rep(s,'points.extend_from_slice(rows)','points.extend_from_slice(&rows)')
    p.write_text(rep(s,'for &i in rows {','for &i in rows.iter() {'))
    p=src/'connected_requests.rs';s=p.read_text()
    s=rep(s,'self.wake_roots(c,src,point,target,&key,join_col)',"""{
                let start=self.profiling.then(std::time::Instant::now);
                let domain=self.wake_roots(c,src,point,target,&key,join_col);
                if let Some(t)=start{self.patch_ports.work.activation_ns+=t.elapsed().as_nanos() as u64;}
                domain
            }""")
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(rep(p.read_text(),anchor,'''        if let Some(mode)=req.get("patch_subscriptions"){
            let n=mode.as_u64().ok_or("invalid subscription setting")?;
            ordinary_witness::configure_patch_ports(n)?;
            if n==3 {runtime.graph.enable_request_union_log();}
        }
'''+anchor))
    p=src/'graph.rs';p.write_text(p.read_text()+'\nimpl Graph {pub fn enable_request_union_log(&mut self){self.request_unions=Some(std::collections::VecDeque::new());}}\n')
