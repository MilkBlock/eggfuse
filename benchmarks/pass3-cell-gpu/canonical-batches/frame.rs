// Only the currently executing root frame can consume these immutable source slots.
// The sparse runtime's native union-generation lifetime is also applied to ordinary storage.
#[derive(Default)]
struct CanonicalFrames {
    mode: u8,
    audit: bool,
    check: bool,
    roles: Vec<(usize, u128, u128)>,
    generation: u64,
    template: usize,
    inputs: u128,
    derived: u128,
    cell: Option<u32>,
    reads: std::cell::Cell<[u64; 2]>,
    activations: u64,
}
impl CanonicalFrames {
    fn begin(&mut self, rid: usize, generation: u64) {
        if self.mode == 0 {
            return;
        }
        let (template, inputs, derived) = self.roles[rid];
        self.template = template;
        self.generation = generation;
        self.inputs = inputs;
        self.derived = if self.mode == 2 { derived } else { 0 };
        self.cell = None;
    }
    fn frame(&mut self, id: u32, template: usize, unions: u64) {
        if self.mode != 0
            && self.template == template
            && self.generation == unions
            && self.inputs | self.derived != 0
        {
            self.cell = Some(id);
            if self.audit {
                self.activations += 1;
            }
        }
    }
    #[inline]
    fn protected(&self, cell: u32, slot: usize) -> Option<usize> {
        if self.cell != Some(cell) || slot >= 128 {
            return None;
        }
        let bit = 1u128 << slot;
        if self.inputs & bit != 0 {
            Some(0)
        } else if self.derived & bit != 0 {
            Some(1)
        } else {
            None
        }
    }
}
impl Graph {
    pub fn configure_canonical_frames(&mut self, mode: u8, audit: bool, check: bool) -> Result<()> {
        if mode > 2 {
            return Err("unknown frame certificate".into());
        }
        self.canon_frames = CanonicalFrames {
            mode,
            audit,
            check,
            ..Default::default()
        };
        if mode == 0 {
            return Ok(());
        }
        let bit = |slot: usize| if slot < 128 { 1u128 << slot } else { 0 };
        self.canon_frames.roles = self
            .program
            .rules
            .iter()
            .map(|r| {
                let template = &self.program.templates[r.template];
                let mut inputs = r.inputs.iter().fold(0u128, |mask, &i| mask | bit(i));
                let mut derived = 0;
                // Materialized values may be read only at slots with one statically checked
                // origin. Reject any input redefinition even if a malformed plan contains one.
                for op in template.ops.iter() {
                    if let Op::Copy(dst, _) | Op::Let(dst, _, _) = op {
                        inputs &= !bit(*dst);
                    }
                }
                for op in template.ops.iter() {
                    match op {
                        Op::Copy(dst, Arg::Slot(src)) if (inputs | derived) & bit(*src) != 0 => {
                            derived |= bit(*dst)
                        }
                        Op::Let(dst, Call::Table(t), _) if self.program.tables[*t].constructor => {
                            derived |= bit(*dst)
                        }
                        _ => (),
                    }
                }
                (r.template, inputs, derived)
            })
            .collect();
        Ok(())
    }
    pub fn frame_proof_report(&self) -> J {
        let v = &self.canon_frames;
        json!({"mode":v.mode,"checked":v.check,
        "activations":v.activations,"reads":v.reads.get(),"input_roles":v.roles.iter().map(|x|x.1.count_ones() as u64).sum::<u64>(),"derived_roles":v.roles.iter().map(|x|x.2.count_ones() as u64).sum::<u64>(),"static_bytes":v.roles.capacity()*std::mem::size_of::<(usize,u128,u128)>()})
    }
}

#[cfg(all(test, not(feature = "sparse-cells")))]
mod canonical_frame_lifecycle {
    use super::*;
    #[test]
    fn real_union_expires_the_regular_source_slot_permission() {
        let program=serde_json::from_value(json!({
            "multi_stage":crate::multistage::MultiStage::default(),"entry_schedule":crate::entry_schedule::Plan::default(),
            "tables":[],"templates":[],"rules":[],"sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{}
        })).unwrap();
        let mut g = Graph::new(program).unwrap();
        g.canon_frames = CanonicalFrames {
            mode: 1,
            roles: vec![(0, 1, 2)],
            ..Default::default()
        };
        g.begin_canonical_rhs(0, g.stats.unions);
        g.canon_frames.frame(42, 0, g.stats.unions);
        assert_eq!(g.canon_frames.protected(42, 0), Some(0));
        assert_eq!(g.canon_frames.protected(41, 0), None);
        assert_eq!(g.canon_frames.protected(42, 1), None);
        let values = std::iter::once((0, Value::Eq(9))).collect();
        assert_eq!(
            g.slot_fields(42, 0, None, &values, None, 0).unwrap(),
            Value::Eq(9)
        );
        g.union(9, 2).unwrap();
        assert_eq!(g.canon_frames.protected(42, 0), None);
        assert_eq!(
            g.slot_fields(42, 0, None, &values, None, 0).unwrap(),
            Value::Eq(2)
        );
        g.canon_frames.frame(43, 0, g.stats.unions);
        assert_eq!(g.canon_frames.protected(43, 0), None);
        g.finish_canonical_rhs();
        g.canon_frames.mode = 2;
        g.begin_canonical_rhs(0, g.stats.unions);
        g.canon_frames.frame(44, 0, g.stats.unions);
        assert_eq!(g.canon_frames.protected(44, 1), Some(1));
        g.finish_canonical_rhs();
        assert_eq!(g.canon_frames.protected(44, 1), None);
    }
}
