impl Graph {
    pub(crate) fn audit_ordered_effect(
        &self,
        template: usize,
        op: usize,
        projected: &Op,
        id: u32,
        local: Option<&Cell>,
    ) -> Result<()> {
        let source = &self.program.templates[template].ops[op];
        let check = |a: &Arg, b: &Arg| -> Result<()> {
            if a == b {
                return Ok(());
            }
            let read = |arg: &Arg| match local {
                Some(c) => self.argument_in(id, c, None, arg),
                None => self.argument(id, arg),
            };
            if read(a)? != read(b)? {
                return Err("ordered effect wire disagrees with source operand".into());
            }
            self.effect_audit_fields
                .set(self.effect_audit_fields.get() + 1);
            Ok(())
        };
        let list = |xs: &[Arg], ys: &[Arg]| -> Result<()> {
            if xs.len() != ys.len() {
                return Err("ordered effect arity differs".into());
            }
            for (a, b) in xs.iter().zip(ys) {
                check(a, b)?
            }
            Ok(())
        };
        match (source, projected) {
            (Op::Let(_, _, xs), Op::Let(_, _, ys)) | (Op::Hide(_, xs, _), Op::Hide(_, ys, _)) => {
                list(xs, ys)
            }
            (Op::Set(_, xs, a), Op::Set(_, ys, b)) => {
                list(xs, ys)?;
                check(a, b)
            }
            (Op::Union(a, b), Op::Union(c, d)) => {
                check(a, c)?;
                check(b, d)
            }
            (Op::Panic, Op::Panic) | (Op::Copy(..), Op::Copy(..)) => Ok(()),
            _ => Err("ordered effect kind differs".into()),
        }
    }
}
