"""Attach realized Cell-id and template to post-commit provenance. Audit-only private native build."""
from pathlib import Path


def replace(p,old,new):
    s=p.read_text()
    if s.count(old)!=1:raise ValueError((p,old[:55],s.count(old)))
    p.write_text(s.replace(old,new))


def install(crate):
    src=Path(crate)/'src';p=src/'graph.rs'
    replace(p,'pub struct Graph {','''pub struct Graph {
    pub joint_allocations: Option<Vec<(usize,u32,usize,Option<usize>,bool)>>,
    pub(crate) joint_issuer: Option<(usize,usize)>,''')
    replace(p,'        let mut g = Self {','''        let mut g = Self {
            joint_allocations: None, joint_issuer: None,''')
    replace(p,'        self.cells.insert(id, cell);','''        if let Some(v)=&mut self.joint_allocations{
            v.push((self.joint_issuer.map_or(0,|x|x.0),id,cell.template,self.joint_issuer.map(|x|x.1),false));
        }
        self.cells.insert(id, cell);''')
    p=src/'writer_frames.rs'
    replace(p,'            self.cells.insert(previous.cell, c);','''            if let Some(v)=&mut self.joint_allocations{
                v.push((self.joint_issuer.map_or(0,|x|x.0),previous.cell,c.template,self.joint_issuer.map(|x|x.1),true));
            }
            self.cells.insert(previous.cell, c);''')
    p=src/'runtime.rs'
    replace(p,'        let result=self.apply_owned(rid,b,','''        if let Some(rows)=&self.allocation_audit {
            self.graph.joint_issuer=Some((rows.len()+1,self.graph.program.rules[rid].template));
        }
        let result=self.apply_owned(rid,b,''')
    replace(p,'        self.graph.end_owner_entry();','''        self.graph.joint_issuer=None;
        self.graph.end_owner_entry();''')
