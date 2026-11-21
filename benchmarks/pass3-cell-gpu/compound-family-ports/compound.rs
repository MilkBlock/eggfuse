#[derive(Default, Serialize)]
struct CompoundWork {
    planned: u64,
    admitted: u64,
    fallback: u64,
    sender_computed: u64,
    sender_reused: u64,
    receiver_computed: u64,
    compound_packets: u64,
    compound_keys: u64,
    compound_bytes: u64,
}
struct ScalarColumn {
    generation: u64,
    union: u64,
    column: Option<Rc<Vec<u32>>>,
}
fn paired_code(primary: u32, secondary: Option<u32>) -> u64 {
    u64::from(primary) | (u64::from(secondary.unwrap_or(0)) << 32)
}
impl Store {
    fn family_scalar_column(
        &mut self,
        c: &Context,
        step: &StackStep,
        eq: &Equation,
        side: usize,
    ) -> Option<Rc<Vec<u32>>> {
        let key = (self.rule, side);
        let frame = &step.frame;
        if let Some(v) = self.family.scalar_columns.get(&key)
            && v.generation == frame.generation
            && v.union == frame.born_at_union
        {
            self.family.compound_work.sender_reused += 1;
            return v.column.clone();
        }
        let mut result = Vec::with_capacity(frame.rows.len());
        let mut known = true;
        for row in &frame.rows {
            self.family.compound_work.sender_computed += 1;
            let Some(v) = self.lazy_equation_value(c, eq, side, row) else {
                known = false;
                break;
            };
            result.push(v);
        }
        let column = known.then(|| Rc::new(result));
        self.family.scalar_columns.insert(
            key,
            ScalarColumn {
                generation: frame.generation,
                union: frame.born_at_union,
                column: column.clone(),
            },
        );
        column
    }
}
