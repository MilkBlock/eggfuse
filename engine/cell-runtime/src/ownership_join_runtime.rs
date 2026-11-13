//! Bounded takeover at a matched Entry. Old runtime arrays and boundary routes
//! are replaced, not retained as children of another ownership graph.
use super::*;

impl Graph {
    pub(in crate::graph::cell_ownership) fn take_over_matched_components(&mut self,rid:usize,anchors:&[Option<Dependency>]) {
        let plans=&self.program.cell_ownership.composition;
        let Some(indices)=plans.join_rules.get(rid).filter(|v|!v.is_empty()) else {return;};

        let Some(m)=self.ownership.as_mut() else {return;};
        if !m.pending.is_empty() || !m.composition.heap.is_empty() || m.composition.components.is_frozen()
            || !self.pending_unions.is_empty() || !self.dirty.is_empty() {
            m.stats.dual_pending_skips+=1;return;
        }
        let mut candidates=smallvec::SmallVec::<[usize;4]>::new();
        for (&(a,b),routes) in indices {
            m.stats.dual_route_probes+=1;
            let key=|entry:usize| {
                let Some(Some(Dependency::Fact(f)))=anchors.get(entry) else {return None;};
                let frame=m.composition.frames.get(&f.cell)?;
                let shape=m.composition.components[frame.component as usize].as_ref()?.shape;
                Some((shape,frame.ordinal,f.op,frame.code))
            };
            if let (Some(a),Some(b))=(key(a),key(b)) {
                if let Some(ids)=routes.get(&[a,b]) {candidates.extend(ids.iter().copied());}
            }
        }
        candidates.sort_unstable();candidates.dedup();
        if candidates.spilled() {m.stats.dual_temporary_bytes+=(candidates.capacity()*std::mem::size_of::<usize>()) as u64;}
        for index in candidates {
            let join=self.program.cell_ownership.composition.joins[index].clone();
            self.ownership.as_mut().unwrap().stats.dual_candidates+=1;
            let m=self.ownership.as_ref().unwrap();
            let mut ids=[None;2];let mut valid=true;
            for &(entry,component,ordinal,op) in &join.pattern.anchors {
                let Some(Some(Dependency::Fact(f)))=anchors.get(entry) else {valid=false;break;};
                let Some(frame)=m.composition.frames.get(&f.cell) else {valid=false;break;};
                if f.op!=op || frame.ordinal!=ordinal
                    || self.cells.fact_state(*f).is_none_or(|s|!s.owned || s.hidden)
                    || ids[component].is_some_and(|id|id!=frame.component) {valid=false;break;}
                ids[component]=Some(frame.component);
            }
            let [Some(left),Some(right)]=ids else {continue;};
            if !valid || left==right {continue;}
            let ids=[left,right];
            for (side,&id) in ids.iter().enumerate() {
                let c=m.composition.components[id as usize].as_ref().unwrap();
                if c.shape!=join.pattern.components[side].0
                    || c.frames.iter().map(|id|m.composition.frames[id].code).ne(join.pattern.components[side].1.iter().copied())
                    || c.frames.iter().any(|id|self.cells.cell_metadata(*id).is_some_and(|meta|!meta.completed)) {
                    valid=false;break;
                }
            }
            if !valid {continue;}
            // All queried aliases must be bound now. A profile is never enough
            // evidence to invent an unbound result or overwrite unequal values.
            for (_,sites) in &join.pattern.shared_slots {
                if sites.iter().any(|&(side,s)|m.composition.components[ids[side] as usize].as_ref().unwrap().signals[s].is_none()) {
                    valid=false;break;
                }
            }
            if !valid {continue;}
            let mut signals=vec![None;join.shape.signals.len()];
            let mut old_bound=0;let mut checks=0;
            for (side,&id) in ids.iter().enumerate() {
                for (symbol,value) in m.composition.components[id as usize].as_ref().unwrap().signals.iter().enumerate() {
                    checks+=1;
                    let Some(value)=value else {continue;};old_bound+=1;
                    let value=m.stats.signal_root(&self.parents,*value);let slot=&mut signals[join.symbol_maps[side][symbol]];
                    if slot.is_some_and(|previous|previous!=value) {valid=false;break;}
                    *slot=Some(value);
                }
            }
            let m=self.ownership.as_mut().unwrap();
            m.stats.dual_symbol_checks+=checks;
            m.stats.dual_temporary_bytes+=(signals.capacity()*std::mem::size_of::<Option<u64>>()) as u64;
            if !valid {continue;}
            let new_bound=signals.iter().filter(|v|v.is_some()).count();
            // Remove the old exact routes while their old class/origin still
            // resolves. Unknown external users remain in the shared new wiring.
            for &id in &ids {
                let c=m.composition.components[id as usize].as_ref().unwrap();
                for (symbol,value) in c.signals.iter().enumerate() {
                    let Some(value)=value else {continue;};let value=m.stats.signal_root(&self.parents,*value);
                    let signal=m.composition.signal(&self.program.cell_ownership,id,symbol);
                    m.stats.boundary_probes+=1;
                    if let Some(set)=m.boundaries.get_mut(&value) {
                        if set.remove(&signal) {m.stats.boundary_live-=1;m.stats.boundary_edges_removed+=1;}
                        if set.is_empty() {m.boundaries.remove(&value);}
                    }
                }
            }
            let mut a=m.composition.components.local_mut(left as usize).take().unwrap();
            let b=m.composition.components.local_mut(right as usize).take().unwrap();
            let old_capacity=if a.frames.spilled() {a.frames.capacity()} else {0};
            let retained_prefix=a.frames.len();
            a.frames.extend(b.frames);
            if a.frames.spilled() && a.frames.capacity()!=old_capacity {
                m.stats.dual_temporary_bytes+=(a.frames.capacity()*std::mem::size_of::<u32>()) as u64;
            }
            drop(b.signals);
            a.shape=join.target;a.signals=signals;
            // Left source addresses are unchanged; only the appended side moves.
            for (ordinal,&cell) in a.frames.iter().enumerate().skip(retained_prefix) {
                let code=m.composition.frames[&cell].code;
                m.composition.frames.insert(cell,Frame{component:left,ordinal,code});
                m.stats.dual_source_moves+=1;
            }
            m.composition.live_facts[left as usize]+=m.composition.live_facts[right as usize];
            m.composition.live_facts[right as usize]=0;
            let frame_count=a.frames.len();
            *m.composition.components.local_mut(left as usize)=Some(a);
            m.stats.components_live-=1;m.stats.components_retired+=1;
            m.stats.signal_bindings_live-=(old_bound-new_bound) as u64;
            m.stats.signal_bindings_retired+=(old_bound-new_bound) as u64;
            m.stats.dual_bindings_retired+=(old_bound-new_bound) as u64;
            m.stats.dual_admissions+=1;
            // Move only cached field locations; actual scalar arrays and fact
            // identities stay in place. No full-row reconstruction or copy.
            for ordinal in retained_prefix..frame_count {
                let cell=self.ownership.as_ref().unwrap().composition.components[left as usize].as_ref().unwrap().frames[ordinal];
                let moved=self.relocate_stable_source(cell,left,ordinal);
                self.ownership.as_mut().unwrap().stats.dual_field_moves+=moved as u64;
            }
            for symbol in 0..join.shape.signals.len() {
                let m=self.ownership.as_ref().unwrap();
                let Some(value)=m.composition.components[left as usize].as_ref().unwrap().signals[symbol] else {continue;};
                let signal=m.composition.signal(&self.program.cell_ownership,left,symbol);
                if !self.signal_is_native(signal,value) {self.boundary(value,signal);}
            }
            return;
        }
    }
}
