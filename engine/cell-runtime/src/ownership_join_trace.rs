//! Successful query Entries can connect several old components. Observe their
//! static wiring without merging owners or retaining instance identities.
use super::*;
#[path="ownership_join_plan.rs"]
mod plan;

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub(super) struct Pattern {
    rule: usize,
    // Component order is first occurrence in query Entry order, not allocation ID.
    components: Vec<(usize, Vec<usize>)>,
    // Entry, component ordinal, source-frame ordinal, fact operation.
    anchors: Vec<(usize, usize, usize, u32)>,
    // Matched query slot -> (component ordinal, shared symbol).
    shared_slots: Vec<(usize, Vec<(usize, usize)>)>,
}
#[derive(Default, Serialize)]
struct Counts { applications: u64, cross_epoch_applications: u64 }
#[derive(Default)]
pub(super) struct Trace {
    entries: u64,
    multi_component_entries: u64,
    disconnected_entries: u64,
    inconsistent_slots: u64,
    dropped_patterns: u64,
    patterns: BTreeMap<Pattern, Counts>,
}
impl Trace {
    pub(super) fn report(&self)->J {
        json!({"schema":"matched-multi-source/v1","entries":self.entries,
            "multi_component_entries":self.multi_component_entries,
            "disconnected_entries":self.disconnected_entries,"inconsistent_slots":self.inconsistent_slots,
            "dropped_patterns":self.dropped_patterns,"pattern_limit":4096,
            "patterns":self.patterns.iter().map(|(pattern,counts)|json!({"pattern":pattern,"counts":counts})).collect::<Vec<_>>(),
            "scope":"successful immutable constructor query receipts connected by a shared Eq query slot; no instance IDs or values retained; no owner merged or RHS skipped",
            "obligations":"partial query coverage; scalar guards, mutable reads, delta ownership, source lifetime and visibility, effect order, boundary users and source-local restoration remain live; cross_epoch is not a Run identity"})
    }
}
impl Graph {
    pub(super) fn observe_component_join(&mut self,rid:usize,anchors:&[Option<Dependency>]) {
        let Some(m)=self.ownership.as_ref().filter(|m|m.composition.catalog_trace.is_some()) else {return;};
        let plan=&self.program.cell_ownership;
        let mut ids=Vec::new();
        let mut pattern=Pattern{rule:rid,components:vec![],anchors:vec![],shared_slots:vec![]};
        let mut slots=BTreeMap::<usize,Vec<(usize,usize,u64)>>::new();
        let mut cross_epoch=false;
        for (entry,anchor) in anchors.iter().enumerate() {
            let Some(Dependency::Fact(f))=anchor else {continue;};
            let query=&self.program.rules[rid].query[plan.entries[rid][entry]];
            let Call::Table(table)=query.call else {continue;};
            if !self.program.tables[table].constructor || !self.program.tables[table].virtual_fact {continue;}
            if self.cells.fact_state(*f).is_none_or(|s|!s.owned || s.hidden) {continue;}
            let Some(frame)=m.composition.frames.get(&f.cell) else {continue;};
            let component=m.composition.components[frame.component as usize].as_ref().unwrap();
            let shape=m.composition.shapes[component.shape].as_ref().unwrap();
            let ordinal=if let Some(i)=ids.iter().position(|&id|id==frame.component) {i} else {
                let i=ids.len();ids.push(frame.component);
                pattern.components.push((component.shape,component.frames.iter().map(|id|m.composition.frames[id].code).collect()));i
            };
            pattern.anchors.push((entry,ordinal,frame.ordinal,f.op));
            cross_epoch|=self.cells.cell_metadata(f.cell).is_some_and(|meta|meta.started_epoch<self.epoch);
            let fields=&plan.programs[shape.programs[frame.ordinal]].fields[f.op as usize];
            for (arg,field) in query.args.iter().zip(fields) {
                let (Arg::Slot(slot),Some(local))=(arg,field) else {continue;};
                let symbol=shape.ports[frame.ordinal][*local];
                if let Some(value)=component.signals[symbol] {
                    slots.entry(*slot).or_default().push((ordinal,symbol,root(&self.parents,value)));
                }
            }
        }
        let trace=&mut self.ownership.as_mut().unwrap().composition.catalog_trace.as_mut().unwrap().joins;
        trace.entries+=1;
        if ids.len()<2 {return;}
        trace.multi_component_entries+=1;
        for (slot,mut sites) in slots {
            sites.sort_unstable();sites.dedup();
            if sites.iter().map(|s|s.0).collect::<BTreeSet<_>>().len()<2 {continue;}
            if sites.iter().any(|s|s.2!=sites[0].2) {trace.inconsistent_slots+=1;return;}
            pattern.shared_slots.push((slot,sites.into_iter().map(|(c,s,_)|(c,s)).collect()));
        }
        if pattern.shared_slots.is_empty() {trace.disconnected_entries+=1;return;}
        if trace.patterns.len()>=4096 && !trace.patterns.contains_key(&pattern) {trace.dropped_patterns+=1;return;}
        let count=trace.patterns.entry(pattern).or_default();
        count.applications+=1;count.cross_epoch_applications+=u64::from(cross_epoch);
    }
}
