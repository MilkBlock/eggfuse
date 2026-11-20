#[derive(Default, Serialize)]
struct LazyWork {
    checks: u64,
    rejected: u64,
    computed: u64,
    undefined: u64,
    fallback: u64,
    left_reused: u64,
    encodes: u64,
    table_hits: u64,
}
#[derive(Default)]
struct LazyEquations {
    mode: u64,
    table: Vec<Option<(i64, u32)>>,
    stats: LazyWork,
}
pub fn configure_lazy(mode: u64) -> Result<()> {
    if !(1..=4).contains(&mode) {
        return Err("unknown lazy equation mode".into());
    }
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing source policy")?;
        if s.equations.mode != 1 {
            return Err(
                "lazy scalar ports require a compiled equation and checked pair path".into(),
            );
        }
        s.lazy_eq.mode = mode;
        if mode == 4 {
            s.lazy_eq.table.resize(256, None);
        }
        Ok(())
    })
}
impl Store {
    fn lazy_equation_value(
        &mut self,
        c: &Context<'_>,
        eq: &Equation,
        side: usize,
        row: &Row,
    ) -> Option<u32> {
        let y = if side == eq.side {
            let [a, b] = eq.from.each_ref().map(|port| match port {
                IntPort::Integer(a) => Some(*a),
                IntPort::Field(i) => match row.values[*i] {
                    Value::Int(a) => Some(a),
                    _ => None,
                },
            });
            let (Some(a), Some(b)) = (a, b) else {
                self.lazy_eq.stats.fallback += 1;
                return None;
            };
            let Call::Primitive(op, ty) = &c.rule.query[eq.atom].call else {
                return None;
            };
            self.lazy_eq.stats.computed += 1;
            let result = if self.lazy_eq.mode == 2 {
                match c.graph.primitive(op, &[Value::Int(a), Value::Int(b)], ty) {
                    Ok(Some(Value::Int(n))) => Some(n),
                    Ok(None) => None,
                    _ => {
                        self.lazy_eq.stats.fallback += 1;
                        return None;
                    }
                }
            } else {
                crate::value::checked_integer_binary(op, a, b)
            };
            let Some(value) = result else {
                self.lazy_eq.stats.undefined += 1;
                return Some(u32::MAX);
            };
            value
        } else {
            match row.values[eq.to] {
                Value::Int(n) => n,
                _ => {
                    self.lazy_eq.stats.fallback += 1;
                    return None;
                }
            }
        };
        // The trained query and key are tied in all views, so a signed integer has
        // the same code for either parent. A collision in this memo only replaces an entry.
        let idx = (y as u64 as usize) & 255;
        if self.lazy_eq.mode == 4
            && let Some((old, word)) = self.lazy_eq.table[idx]
            && old == y
        {
            self.lazy_eq.stats.table_hits += 1;
            return Some(word);
        }
        let word = signature(self.code(&Value::Int(y)), side == 0, self.views);
        self.lazy_eq.stats.encodes += 1;
        if self.lazy_eq.mode == 4 {
            self.lazy_eq.table[idx] = Some((y, word));
        }
        Some(word)
    }
}
