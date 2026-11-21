"""Retain original ordered slot semantics and vary only Cell.facts backing."""
from pathlib import Path


def change(s, old, new):
    if s.count(old) != 1:
        raise ValueError(old)
    return s.replace(old, new)


def install(crate):
    src = crate / 'src'
    p = crate / 'Cargo.toml'
    p.write_text(change(p.read_text(), '[features]', '[features]\nfact-lane-1=[]\nfact-lane-2=[]'))
    p = src / 'slots.rs'
    s = p.read_text()
    fact_map = s[:s.index('#[cfg(test)]')].replace(
        'pub type Slots = FrameMap<usize, crate::value::Value>;', '')
    fact_map = change(fact_map, 'pub struct FrameMap<K, V>(Vec<(K, V)>);',
                      'pub struct FrameMap<K,V>(smallvec::SmallVec<[(K,V);super::FACT_LANES]>);')
    fact_map = change(fact_map, 'std::vec::IntoIter<Self::Item>',
                      'smallvec::IntoIter<[(K,V);super::FACT_LANES]>')
    fact_map = change(fact_map, 'Self(Vec::new())', 'Self(smallvec::SmallVec::new())')
    fact_map = change(fact_map, 'Self(Vec::with_capacity(it.size_hint().0))',
                      'Self(smallvec::SmallVec::with_capacity(it.size_hint().0))')
    fact_map = change(fact_map, 'self.0.capacity() * std::mem::size_of::<(K, V)>()',
                      'if self.0.spilled(){self.0.capacity()*std::mem::size_of::<(K,V)>()}else{0}')
    fact_map += """
impl<K,V> FrameMap<K,V>{
    pub(crate) fn stage_reserved(n:usize)->Self{Self(smallvec::SmallVec::with_capacity(n))}
    pub(crate) fn stage_allocation(&self)->usize{self.0.as_ptr() as usize}
    pub(crate) fn stage_bytes(&self)->usize{
        if self.0.spilled(){self.0.capacity()*std::mem::size_of::<(K,V)>()}else{0}
    }
    pub(crate) fn stage_inline(&self)->bool{!self.0.spilled()}
    pub(crate) fn stage_move_from(&mut self,src:Self){assert!(self.0.is_empty());self.0.extend(src.0);}
}
"""
    (src / 'inline_fact_map.rs').write_text(fact_map)
    p.write_text(s + """
#[cfg(any(feature="fact-lane-1",feature="fact-lane-2"))]
#[path="inline_fact_map.rs"]
mod inline_fact_map;
#[cfg(feature="fact-lane-1")]
pub const FACT_LANES:usize=1;
#[cfg(feature="fact-lane-2")]
pub const FACT_LANES:usize=2;
#[cfg(not(any(feature="fact-lane-1",feature="fact-lane-2")))]
pub const FACT_LANES:usize=0;
#[cfg(any(feature="fact-lane-1",feature="fact-lane-2"))]
pub type CellFacts=inline_fact_map::FrameMap<u32,crate::graph::FactState>;
#[cfg(not(any(feature="fact-lane-1",feature="fact-lane-2")))]
pub type CellFacts=FrameMap<u32,crate::graph::FactState>;
impl<K,V> FrameMap<K,V>{pub(crate) fn stage_inline(&self)->bool{false}}
""")
    p = src / 'graph.rs'
    s = change(p.read_text(),'pub facts: crate::slots::FrameMap<u32, FactState>,',
               'pub facts: crate::slots::CellFacts,')
    p.write_text(s + """
impl Graph {
    pub fn fact_lane_report(&self)->serde_json::Value{
        let mut inline=0usize;
        let mut heap=0usize;
        let mut heap_bytes=0usize;
        let mut facts=0usize;
        let mut empty=0usize;
        for c in self.cells.values(){
            facts+=c.facts.len();
            empty+=usize::from(c.facts.is_empty());
            inline+=usize::from(c.facts.stage_inline());
            heap+=usize::from(c.facts.stage_bytes()>0);
            heap_bytes+=c.facts.stage_bytes();
        }
        serde_json::json!({"lanes":crate::slots::FACT_LANES,"cell_size":std::mem::size_of::<Cell>(),
            "fact_entry_size":std::mem::size_of::<(u32,FactState)>(),"cells":self.cells.len(),"facts":facts,
            "empty":empty,"inline":inline,"heap_buffers":heap,"heap_capacity_bytes":heap_bytes})
    }
}
""")
    p = src / 'speculative_staging.rs'
    s = change(p.read_text(), 'facts: crate::slots::FrameMap::stage_reserved(facts),',
               'facts: crate::slots::CellFacts::stage_reserved(facts),')
    s = change(s, '    slabs: Vec<Vec<PrivateSlot>>,',
               '    defer_facts:bool,\n    slabs: Vec<Vec<PrivateSlot>>,')
    s = change(s, '            slabs: vec![],',
               '            defer_facts:cfg["defer_facts"]==true,\n            slabs: vec![],')
    s = change(s, '            let facts = g.program.templates[template].ops.len().clamp(1, 4);',
               '            let facts = if self.defer_facts{0}else{g.program.templates[template].ops.len().clamp(1,4)};')
    s = change(s, '    payload_identity: usize,', '''    payload_identity: usize,
    inline_at_birth:usize, heap_at_birth:usize, unallocated_at_birth:usize,
    inline_address_preserved:usize, inline_address_moved:usize, early_heap_preserved:usize,
    early_heap_relocated:usize, selected_unallocated:usize, inline_spilled_at_publication:usize,''')
    # Sample actual final backing address inside the slab. Vec::with_capacity(count)
    # and one push per granted record guarantee that subsequent pushes cannot move it.
    s = change(s, '                let (frame, ptr) = if self.storage != Storage::Capacity {',
               '                let frame = if self.storage != Storage::Capacity {')
    s = change(s,'                    let ptr = c.facts.stage_allocation();','''                    if c.facts.stage_inline(){self.stats.inline_at_birth+=1}
                    else if c.facts.stage_bytes()!=0{self.stats.heap_at_birth+=1}
                    else{self.stats.unallocated_at_birth+=1}''')
    s = change(s,'                    (Some(c), ptr)','                    Some(c)')
    s = change(s,'                    (None, 0)','                    None')
    s = change(s,'                    fact_ptr: ptr,\n                });','''                    fact_ptr: 0,
                });
                let slot=slab.last_mut().unwrap();
                if let Some(c)=&slot.frame && (c.facts.stage_inline() || c.facts.stage_bytes()>0){
                    slot.fact_ptr=c.facts.stage_allocation();
                }''')
    s = change(s,'    pub early_ptr: usize,','    pub early_ptr: usize,\n    pub early_inline:bool,')
    s = change(s,'            early_ptr: slot.fact_ptr,','            early_ptr: slot.fact_ptr,\n            early_inline,')
    s = change(s,'        let frame = slot.frame.take().unwrap();','''        let early_inline=slot.frame.as_ref().unwrap().facts.stage_inline();
        let frame = slot.frame.take().unwrap();''')
    s = change(s,'old_ptr: usize, early: bool, direct: bool','old_ptr: usize, early_inline:bool, early: bool, direct: bool')
    s = change(s,'            if old_ptr == stored.facts.stage_allocation() {','''            if old_ptr==0{
                stage.stats.selected_unallocated+=1;
            }else if early_inline{
                if stored.facts.stage_inline() {
                    if old_ptr==stored.facts.stage_allocation() {stage.stats.inline_address_preserved+=1;stage.stats.payload_identity+=1;}
                    else {stage.stats.inline_address_moved+=1;}
                }else{stage.stats.inline_spilled_at_publication+=1;}
            }else if old_ptr == stored.facts.stage_allocation() {
                stage.stats.early_heap_preserved+=1;''')
    s = change(s,'            } else if stage.audit && stored.facts.is_empty() {\n                panic!("unused staged payload allocation replaced")','''            } else {
                stage.stats.early_heap_relocated+=1;
                if stage.audit && stored.facts.is_empty(){panic!("reserved heap payload relocated before first use")}''')
    s=s.replace('claimed.early_ptr, claimed.preconstructed','claimed.early_ptr, claimed.early_inline, claimed.preconstructed')
    if (src/'resident_cell_pages.rs').is_file():
        s=change(s,'let facts=g.program.templates[t].ops.len().clamp(1,4);',
                 'let facts=if self.defer_facts{0}else{g.program.templates[t].ops.len().clamp(1,4)};')
        anchor='                    self.bytes+=bytes;self.stats.private_payload_capacity_bytes+=bytes;'
        s=change(s,anchor,anchor+'''
                    if c.facts.stage_inline(){self.stats.inline_at_birth+=1}
                    else if bytes>0{self.stats.heap_at_birth+=1}
                    else{self.stats.unallocated_at_birth+=1}''')
        s=change(s,'backing:Backing::Resident(i),early_ptr:0,preconstructed:true','backing:Backing::Resident(i),early_ptr:0,early_inline:false,preconstructed:true')
        s=change(s,'let early=match claim.backing{','let (early,early_inline)=match claim.backing{')
        s=change(s,'self.store_cell(id,c);claim.early_ptr','self.store_cell(id,c);(claim.early_ptr,claim.early_inline)')
        s=change(s,'let (template,parent)={','let (template,parent,was_inline)={')
        s=change(s,'init(c);(c.template,c.parent)','let inline=c.facts.stage_inline(); init(c);(c.template,c.parent,inline)')
        s=change(s,'self.cells.publish(id,i)','(self.cells.publish(id,i),was_inline)')
        s=change(s,'self.check_private(id,early,claim.preconstructed,direct);',
                 'self.check_private(id,early,early_inline,claim.preconstructed,direct);')
        resident=src/'resident_cell_pages.rs'
        rs=change(resident.read_text(),'self.fact_buffer = c.facts.stage_allocation();',
                  'self.fact_buffer = if c.facts.stage_bytes()>0 || c.facts.stage_inline(){c.facts.stage_allocation()}else{0};')
        rs=change(rs,'usize::from(fact_buffer == c.facts.stage_allocation())',
                  'usize::from(fact_buffer!=0 && fact_buffer == c.facts.stage_allocation())')
        resident.write_text(rs)
    else:
        graph=src/'graph.rs';graph.write_text(change(graph.read_text(),'staged.early_ptr,staged.preconstructed',
                                                    'staged.early_ptr,staged.early_inline,staged.preconstructed'))
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs'
    marker='        report["spec_cells"]=runtime.graph.spec_cells_report();'
    p.write_text(change(p.read_text(), marker, marker+'\n        report["fact_lanes"]=runtime.graph.fact_lane_report();'))
    with (src/'slots.rs').open('a') as f:f.write((Path(__file__).parent/'tests.rs').read_text())
