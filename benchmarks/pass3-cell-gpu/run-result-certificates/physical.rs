impl Graph {
    // Both decoders use the same linked instruction and canonical slot accessor.
    fn certificate_fact_args(&self, f: FactRef, c: &Cell) -> Result<(usize, &[Arg], Arg)> {
        let op = self.program.templates[c.template]
            .ops
            .get(f.op as usize)
            .ok_or("invalid live fact position")?;
        match op {
            Op::Let(dst, Call::Table(t), args) => Ok((*t, args, Arg::Slot(*dst))),
            Op::Set(t, args, v) => Ok((*t, args, v.clone())),
            _ => Err("invalid fact recipe position".into()),
        }
    }
    pub(crate) fn compare_certificate_row(
        &self,
        old: &Row,
        compressed: bool,
    ) -> Result<Option<(bool, usize)>> {
        fn stored(fields: &RowFields, old: &Row, compare: bool) -> Option<(bool, usize)> {
            if std::ptr::eq(&fields[..], &old.values[..]) {
                Some((true, 1))
            } else if compare {
                Some((fields == &old.values, 2))
            } else {
                None
            }
        }
        match old.witness {
            Dependency::Function(id) => {
                let Some(f) = self.functions.get(id) else {
                    return Ok(Some((false, 0)));
                };
                if !f.live || f.table != old.table || f.epoch != old.epoch {
                    return Ok(Some((false, 0)));
                }
                if let Some(fields) = &self.function_decoded[id] {
                    return Ok(stored(fields, old, compressed));
                }
                // The nullary unit store can supply an alternate payload.
                if !compressed || f.key.is_empty() || f.key.len() + 1 != old.values.len() {
                    return Ok(None);
                }
                let same = f
                    .key
                    .iter()
                    .chain(std::iter::once(&f.value))
                    .zip(old.values.iter())
                    .all(|(v, expected)| canon(v, &self.parents) == *expected);
                Ok(Some((same, 4)))
            }
            Dependency::Fact(f) => {
                let Some(c) = self.cells.get(&f.cell) else {
                    return Ok(Some((false, 0)));
                };
                let Some(state) = c.facts.get(&f.op) else {
                    return Ok(Some((false, 0)));
                };
                if state.hidden || state.epoch != old.epoch {
                    return Ok(Some((false, 0)));
                }
                if self.stable_node(f).is_some() {
                    return Ok(None);
                }
                if let Some((t, fields)) = &state.decoded {
                    if *t != old.table {
                        return Ok(Some((false, 0)));
                    }
                    return Ok(stored(fields, old, compressed));
                }
                if !compressed {
                    return Ok(None);
                }
                let (table, args, result) = self.certificate_fact_args(f, c)?;
                if table != old.table || args.len() + 1 != old.values.len() {
                    return Ok(Some((false, 0)));
                }
                for (a, expected) in args
                    .iter()
                    .chain(std::iter::once(&result))
                    .zip(old.values.iter())
                {
                    if self.argument_in(f.cell, c, None, a)? != *expected {
                        return Ok(Some((false, 3)));
                    }
                }
                Ok(Some((true, 3)))
            }
        }
    }
}
