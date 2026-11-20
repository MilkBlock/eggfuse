// A page owns the ordered, immutable pointers for one source rule occurrence.
// The source row verifier reads this same storage, including for rejected tuples.
#[derive(Clone, Debug)]
pub(crate) struct MultiPage(Rc<MultiPageData>);

#[derive(Debug)]
struct MultiPageData {
    run: u64,
    first_serial: u64,
    width: usize,
    count: usize,
    layout: Rc<Layout>,
    template: usize,
    refs: Vec<Ref>,
    withheld: bool,
    invalid_version: bool,
}

impl MultiPage {
    pub(crate) fn count(&self) -> usize {
        self.0.count
    }

    fn slice(&self, slot: usize) -> Option<&[Ref]> {
        if slot >= self.0.count {
            return None;
        }
        let begin = slot.checked_mul(self.0.width)?;
        self.0.refs.get(begin..begin.checked_add(self.0.width)?)
    }

    pub(crate) fn parents(&self, slot: usize) -> &[Ref] {
        self.slice(slot).expect("sealed multi-witness slot")
    }

    pub(crate) fn recipe(&self, slot: usize) -> Option<Recipe> {
        (!self.0.withheld).then(|| Recipe(Body::MultiPage(self.clone(), slot)))
    }

    fn decode(&self, slot: usize) -> Option<Decoded> {
        let p = &self.0;
        let mut refs = self.slice(slot)?.to_vec();
        if p.invalid_version {
            let first = refs.first_mut()?;
            first.version = first.version.wrapping_add(1);
        }
        Some(Decoded {
            serial: p.first_serial.checked_add(u64::try_from(slot).ok()?)?,
            origin: "multi",
            run: p.run,
            layout: p.layout.clone(),
            template: p.template,
            refs,
            ports: None,
        })
    }
}

pub(crate) fn multi_page(
    run: u64,
    rid: usize,
    width: usize,
    refs: Vec<Ref>,
    fault: u8,
) -> Result<MultiPage> {
    if width < 2 || refs.is_empty() || refs.len() % width != 0 {
        return Err("incomplete multi-parent page".into());
    }
    STATE.with_borrow_mut(|s| {
        let st = s
            .as_mut()
            .ok_or("resident multi-parent page requires a root issuer")?;
        if !matches!(st.encoding, Encoding::Resident | Encoding::CheckedSlots) {
            return Err("multi-parent page requires resident root encoding".into());
        }
        let layout = st.layout.get(rid).ok_or("invalid page rule")?.clone();
        let first_serial = st.serial.checked_add(1).ok_or("root serial overflow")?;
        let count = refs.len() / width;
        let template = if st.mode == "wrong-template" || fault == 2 {
            layout.template.wrapping_add(1)
        } else {
            layout.template
        };
        let invalid_version = st.mode == "wrong-port" || fault == 1;
        let withheld = st.mode == "withhold" || fault == 3;
        for entry in refs.chunks_exact(width) {
            st.serial += 1;
            for word in [
                st.serial,
                run,
                rid as u64,
                layout.template as u64,
                width as u64,
            ] {
                st.raw = (st.raw ^ word).wrapping_mul(1099511628211);
            }
            for r in entry {
                let (tag, id) = match r.row {
                    Dependency::Fact(f) => (1, (u64::from(f.cell) << 32) | u64::from(f.op)),
                    Dependency::Function(i) => (2, i as u64),
                };
                for word in [r.atom as u64, tag, id, r.version] {
                    st.raw = (st.raw ^ word).wrapping_mul(1099511628211);
                }
            }
        }
        st.emitted[1] += count as u64;
        Ok(MultiPage(Rc::new(MultiPageData {
            run,
            first_serial,
            width,
            count,
            layout,
            template,
            refs,
            withheld,
            invalid_version,
        })))
    })
}
