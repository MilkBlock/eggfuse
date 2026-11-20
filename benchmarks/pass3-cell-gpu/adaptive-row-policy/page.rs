// Pre-verified shared single-witness batch: eight little-endian header words, followed by
// one (tag, address, version) triple per *issued* candidate. Static projection lives in Layout.
#[derive(Clone, Debug)]
pub(crate) struct RootPage {
    layout: Rc<Layout>,
    words: Rc<[u64]>,
}
impl RootPage {
    pub(crate) fn at(&self, slot: usize) -> Recipe {
        Recipe(Body::RowPage(self.clone(), slot))
    }
    fn decode(&self, slot: usize) -> Option<Decoded> {
        let w = &self.words;
        if w.len() < 8
            || w[0] != 0x33524345
            || w[7] as usize <= slot
            || (w[7] as usize).checked_mul(3)?.checked_add(8)? != w.len()
        {
            return None;
        }
        let rid = usize::try_from(w[3]).ok()?;
        let layout = STATE.with_borrow(|s| s.as_ref()?.layout.get(rid).cloned())?;
        if !Rc::ptr_eq(&layout, &self.layout) {
            return None;
        }
        let i = 8 + 3 * slot;
        let refs = match w[i] {
            0 => vec![],
            1 | 2 => {
                let row = if w[i] == 1 {
                    Dependency::Fact(crate::graph::FactRef {
                        cell: (w[i + 1] >> 32) as u32,
                        op: w[i + 1] as u32,
                    })
                } else {
                    Dependency::Function(usize::try_from(w[i + 1]).ok()?)
                };
                vec![Ref {
                    atom: usize::try_from(w[5]).ok()?,
                    row,
                    version: w[i + 2],
                }]
            }
            _ => return None,
        };
        Some(Decoded {
            serial: w[1] + u64::try_from(slot).ok()?,
            origin: "single",
            run: w[2],
            layout,
            template: usize::try_from(w[4]).ok()?,
            refs,
            ports: None,
        })
    }
}
pub(crate) fn single_page(
    run: u64,
    rid: usize,
    atom: Option<usize>,
    inputs: &[(Option<Dependency>, u64)],
) -> Option<RootPage> {
    STATE.with_borrow_mut(|s| {
        let state = s.as_mut()?;
        let layout = state.layout.get(rid)?.clone();
        if inputs.is_empty() {
            return None;
        }
        let first = state.serial + 1;
        let template = if state.mode == "wrong-template" {
            layout.template.wrapping_add(1)
        } else {
            layout.template
        };
        let mut words = Vec::with_capacity(8 + 3 * inputs.len());
        words.extend([
            0x33524345,
            first,
            run,
            rid as u64,
            template as u64,
            atom.map_or(u64::MAX, |a| a as u64),
            1,
            inputs.len() as u64,
        ]);
        for &(dep, version) in inputs {
            state.serial += 1;
            let (mut tag, addr) = match dep {
                Some(Dependency::Fact(f)) => (1, (u64::from(f.cell) << 32) | u64::from(f.op)),
                Some(Dependency::Function(i)) => (2, i as u64),
                None => (0, 0),
            };
            for word in [
                state.serial,
                run,
                rid as u64,
                layout.template as u64,
                u64::from(dep.is_some()),
            ] {
                state.raw = (state.raw ^ word).wrapping_mul(1099511628211);
            }
            if let Some(a) = atom
                && dep.is_some()
            {
                for word in [a as u64, tag, addr, version] {
                    state.raw = (state.raw ^ word).wrapping_mul(1099511628211);
                }
            }
            let mut v = version;
            if state.mode == "wrong-port" {
                if tag == 0 {
                    tag = 2;
                }
                v = v.wrapping_add(1);
            }
            words.extend([tag, addr, v]);
        }
        state.emitted[0] += inputs.len() as u64;
        if state.mode == "withhold" {
            return None;
        }
        state.wire_bytes += (words.len() * 8) as u64;
        if state.audit {
            for &word in &words {
                state.wire_hash = (state.wire_hash ^ word).wrapping_mul(1099511628211);
            }
        }
        Some(RootPage {
            layout,
            words: words.into(),
        })
    })
}
