//! Move the graph-facing state of one execution across a suspension. Private
//! slots keep their allocation; any slots already referenced by the graph stay
//! graph-addressable. Source effect order remains the caller's responsibility.
use super::*;

#[must_use = "a suspended RHS must be resumed before its lifecycle hold is released"]
pub(crate) struct Suspended {
    #[cfg(feature = "slot-transfer-audit")]
    source: Option<(u64, usize)>,
    cell: u32,
    pub(crate) private: Option<Cell>,
    origin: Option<usize>,
    sealed: Option<u64>,
    generation: Option<u64>,
    epoch: u64,
    entry: Option<cell_ownership::composition::Entry>,
    /// Existing Cell lifecycle accounting protects either a private frame's
    /// parent, or the public frame itself. It creates no reverse dependency.
    hold: Option<u32>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{cell::{Effects, RhsFrame}, program::Rule, slots::Slots};
    use std::{rc::Rc, sync::Arc};

    fn graph() -> Graph {
        let mut g = crate::query::test_projection_graph();
        let template = Template { name: "parked-writer".into(),
            sorts: vec![json!({"kind":"i64"}); 4], defs: BTreeMap::new(),
            parent_columns: BTreeMap::new(), ops: Arc::new(vec![
                Op::Set(0, vec![Arg::Slot(0), Arg::Slot(1)], Arg::Slot(2)),
                Op::Set(1, vec![Arg::Slot(0), Arg::Slot(1)], Arg::Slot(2)),
            ]) };
        g.program.templates.push(template.clone());
        g.program.templates.push(Template { name:"parked-child".into(),
            parent_columns:BTreeMap::from([(0,0)]), ..template });
        for template in 0..2 {
            g.program.rules.push(Rule { template, query:Rc::new(vec![]), inputs:vec![0,1,2].into(),
                completion:Default::default(), seminaive:false, direct:None });
        }
        g.program.repair_ports = crate::graph::repair_ports::Plan::derive(&g.program);
        g
    }
    fn begin(g: &mut Graph, template: usize, value: i64, parent: Option<FactRef>) -> u32 {
        let mut values = Slots::with_capacity(4);
        values.extend([(0,Value::Int(1)), (1,Value::Int(2)), (2,Value::Int(value))]);
        g.begin_transient(template,values,parent).unwrap()
    }
    fn write(g: &mut Graph, cell: u32, op: usize) {
        let instruction = g.program.templates[g.rhs_frame(cell).unwrap().template].ops[op].clone();
        (RhsFrame { cell, receipts:&mut Effects::default() }).execute(g,op,&instruction,None).unwrap();
        g.rhs_frame_mut(cell).unwrap().completed_prefix = op + 1;
    }

    #[test]
    fn two_private_owners_keep_allocations_entries_and_individual_union_certificates() {
        let mut g = graph();
        g.use_cell_ownership().unwrap();
        g.sealed_generation = Some(g.stats.unions);
        let a = begin(&mut g,0,7,None);
        g.rhs_frame_mut(a).unwrap().values.insert(3,Value::Eq(9));
        let allocation = std::ptr::from_ref(g.rhs_frame(a).unwrap().values.get(&0).unwrap());
        let anchors = [Some(Dependency::Function(7)),None].into_iter().collect();
        g.begin_owner_entry(0,anchors);
        let a_state = g.suspend_rhs(a);
        assert!(g.rhs_frame(a).is_none());
        assert!(g.take_owner_entry().is_none());
        assert_eq!(g.sealed_generation,None);
        g.sealed_generation = Some(g.stats.unions);
        let b = begin(&mut g,1,8,None);
        g.begin_owner_entry(1,[Some(Dependency::Function(8))].into_iter().collect());
        let b_state = g.suspend_rhs(b);
        assert!(g.active_rhs.is_none());
        g.union(9,2).unwrap();
        // A later batch's certificate must not re-authorize old Eq values.
        g.sealed_generation = Some(g.stats.unions);
        g.restore_rhs(a_state);
        assert_eq!(g.slot(a,3).unwrap(),Value::Eq(2));
        assert_eq!(g.sealed_input_cell,None);
        assert_ne!(g.sealed_generation,Some(g.stats.unions));
        assert_eq!(std::ptr::from_ref(g.rhs_frame(a).unwrap().values.get(&0).unwrap()),allocation);
        let entry = g.take_owner_entry().unwrap();
        assert_eq!((entry.rule,entry.template),(0,0));
        assert_eq!(entry.anchors.as_slice(),[Some(Dependency::Function(7)),None]);
        g.release_empty(a);
        g.restore_rhs(b_state);
        assert_eq!(g.slot(b,2).unwrap(),Value::Int(8));
        let entry = g.take_owner_entry().unwrap();
        assert_eq!((entry.rule,entry.template),(1,1));
        assert_eq!(entry.anchors.as_slice(),[Some(Dependency::Function(8))]);
        g.release_empty(b);
        assert_eq!(g.stats.rhs_suspend_private,2);
        assert_eq!(g.stats.rhs_suspend_promotions,0);
        assert_eq!(g.stats.rhs_suspend_invalidated,2);
    }

    #[test]
    fn published_writer_survives_replacement_and_collection_while_its_owner_waits() {
        let mut g = graph();
        let a = begin(&mut g,0,7,None);
        write(&mut g,a,0);
        let allocation = std::ptr::from_ref(g.rhs_frame(a).unwrap().values.get(&0).unwrap());
        let a_state = g.suspend_rhs(a);
        assert!(a_state.private.is_none());
        assert_eq!(g.slot(a,2).unwrap(),Value::Int(7),"published origin stays addressable");
        let b = begin(&mut g,0,8,None);
        write(&mut g,b,0);
        g.release_empty(b);
        g.collect_garbage();
        assert!(g.cells.contains_key(&a),"the suspended owner retains its public frame");
        g.restore_rhs(a_state);
        assert_eq!(g.rhs_frame(a).unwrap().completed_prefix,1);
        assert_eq!(std::ptr::from_ref(g.rhs_frame(a).unwrap().values.get(&0).unwrap()),allocation);
        write(&mut g,a,1);
        assert_eq!(g.lookup_canonical(0,&[Value::Int(1),Value::Int(2)]).unwrap().unwrap().values.last(),Some(&Value::Int(8)));
        assert_eq!(g.lookup_canonical(1,&[Value::Int(1),Value::Int(2)]).unwrap().unwrap().values.last(),Some(&Value::Int(7)));
        g.release_empty(a);
        assert_eq!(g.stats.rhs_suspend_promotions,1);
        assert_eq!(g.stats.rhs_suspend_public,1);
        assert_eq!(g.stats.rhs_suspend_holds,g.stats.rhs_suspend_releases);
    }

    #[test]
    fn private_parent_projection_survives_deleted_origin_and_collection() {
        let mut g = graph();
        let parent = begin(&mut g,0,7,None);
        write(&mut g,parent,0);
        g.release_empty(parent);
        let child = begin(&mut g,1,8,Some(FactRef { cell:parent,op:0 }));
        let parked = g.suspend_rhs(child);
        assert!(parked.private.is_some());
        assert!(g.hide(0,&[Value::Int(1),Value::Int(2)],true).unwrap());
        g.collect_garbage();
        g.restore_rhs(parked);
        assert_eq!(g.slot(child,0).unwrap(),Value::Int(1),"captured parent input remains valid after deletion");
        g.release_empty(child);
        g.collect_garbage();
        assert!(!g.cells.contains_key(&parent));
        assert_eq!(g.stats.rhs_suspend_holds,1);
        assert_eq!(g.stats.rhs_suspend_releases,1);
    }
}

impl Graph {
    pub(crate) fn suspend_rhs(&mut self, cell: u32) -> Suspended {
        assert!(self.active_rhs.as_ref().is_none_or(|(id, _)| *id == cell),
            "cannot suspend another active RHS");
        assert!(self.rhs_frame(cell).is_some(), "missing executing Cell");
        self.stats.rhs_context_suspends += 1;
        // Function origins and child frames can already address this frame.
        // Its published portion must remain readable while the owner waits.
        if self.active_rhs.is_some() && self.parent_users.get(&cell).copied().unwrap_or(0) > 0 {
            self.promote_active();
            self.stats.rhs_suspend_promotions += 1;
        }
        let private = self.active_rhs.take().map(|(_, frame)| frame);
        let hold = if let Some(frame) = &private {
            self.stats.rhs_suspend_private += 1;
            frame.parent.map(|p| p.cell)
        } else {
            self.stats.rhs_suspend_public += 1;
            Some(cell)
        };
        if let Some(hold) = hold {
            self.retain_cell(hold);
            self.stats.rhs_suspend_holds += 1;
        }
        let sealed = (self.sealed_input_cell == Some(cell)).then_some(self.stats.unions);
        self.sealed_input_cell = None;
        Suspended {
            #[cfg(feature = "slot-transfer-audit")]
            source:crate::transfer_audit::suspend_source(),
            cell, private, hold, sealed, generation: self.sealed_generation.take(), epoch:self.epoch,
            origin: self.active_origin.take(),
            entry: self.take_owner_entry() }
    }

    pub(crate) fn restore_rhs(&mut self, suspended: Suspended) {
        #[cfg(feature = "slot-transfer-audit")]
        crate::transfer_audit::restore_source(suspended.source);
        assert_eq!(self.epoch, suspended.epoch, "a suspended source RHS cannot cross its Run boundary");
        assert!(self.active_rhs.is_none(), "finish or suspend the attached RHS before restoring another");
        let Suspended { cell, private, origin, sealed, generation, entry, hold, .. } = suspended;
        self.restore_owner_entry(entry);
        self.active_rhs = private.map(|frame| (cell, frame));
        assert!(self.rhs_frame(cell).is_some(), "suspended public frame was retired");
        self.active_origin = origin;
        self.sealed_generation = generation;
        // A newly sealed Run cannot re-certify older captured inputs. Only the
        // certificate that travelled with this execution can be restored.
        self.sealed_input_cell = sealed.filter(|&generation| generation == self.stats.unions).map(|_| cell);
        self.stats.rhs_suspend_invalidated += u64::from(sealed.is_some() && self.sealed_input_cell.is_none());
        if let Some(hold) = hold {
            self.release_cell(hold);
            self.stats.rhs_suspend_releases += 1;
        }
        self.stats.rhs_context_resumes += 1;
    }
}
