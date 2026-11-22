// Input slots of each pure predicate are columns of the same witnessed row.
struct RowGuard {
    name: String,
    dst: usize,
    args: [Arg; 2],
}

impl RowGuard {
    fn compile(query: &[crate::program::Atom]) -> Option<Vec<Self>> {
        let row = query.first()?;
        let mut guards = Vec::new();
        for test in &query[1..] {
            let Call::Primitive(name, out) = &test.call else {
                return None;
            };
            if out != "Unit" || !matches!(name.as_str(), "<" | "<=" | ">" | ">=") {
                return None;
            }
            let [left, right, Arg::Slot(dest)] = test.args.as_slice() else {
                return None;
            };
            if row.args.iter().any(|a| matches!(a,Arg::Slot(s) if s==dest)) {
                return None;
            }
            let resolve = |a: &Arg| match a {
                Arg::Slot(s) => row
                    .args
                    .iter()
                    .position(|r| matches!(r,Arg::Slot(i) if s==i))
                    .map(Arg::Slot),
                Arg::Literal(crate::value::Value::Int(_)) => Some(a.clone()),
                _ => None,
            };
            guards.push(Self {
                name: name.clone(),
                dst: *dest,
                args: [resolve(left)?, resolve(right)?],
            });
        }
        Some(guards)
    }
    fn accepts(
        &self,
        g: &Graph,
        values: &[crate::value::Value],
    ) -> Result<Option<crate::value::Value>> {
        let args = self.args.each_ref().map(|arg| match arg {
            Arg::Slot(i) => values[*i].clone(),
            Arg::Literal(v) => v.clone(),
        });
        g.primitive(&self.name, &args, "Unit")
    }
}
