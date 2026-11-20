#[derive(Default, serde::Serialize)]
struct LeanRootStats {
    // A field access is still made for every RHS input even in grouped mode.
    single_binds: u64,
    multi_binds: u64,
    projected_values: u64,
    skipped_atom_checks: u64,
    produced_refs: u64,
    archived_refs: u64,
    raw_omitted: u64,
    typed_rows: u64,
    wire_bytes_avoided: u64,
    fused_header_reads: u64,
}

pub fn configure_lean_root(bits: u64) -> Result<()> {
    if bits > 31 || bits & 28 != 0 && bits & 2 == 0 {
        return Err("invalid root receipt options".into());
    }
    STATE.with_borrow_mut(|s| {
        let state = s.as_mut().ok_or("missing root issuer")?;
        if !matches!(state.encoding, Encoding::CheckedSlots) {
            return Err("borrowed roots require checked slots".into());
        }
        state.lean = bits as u8;
        Ok(())
    })
}

impl State {
    fn record_fingerprint(&self) -> bool {
        self.audit || self.lean & 1 == 0
    }
}

fn borrowed_page(packet: &Recipe) -> bool {
    matches!(
        packet.0,
        Body::RowPage(..) | Body::MultiPage(..) | Body::Typed(..)
    ) && STATE.with_borrow(|state| state.as_ref().is_some_and(|s| s.lean & 2 != 0))
}

// Both packet forms bind against the same immutable source epoch. Only the
// independent source rows are retained in a detailed-audit object after binding.
fn bind_page(
    packet: &Recipe,
    graph: &Graph,
    rid: usize,
    known: impl Fn(usize) -> Option<Dependency>,
    verified: &Slots,
) -> Result<Option<Rc<Bound>>> {
    let reject = || {
        STATE.with_borrow_mut(|s| s.as_mut().unwrap().rejected += 1);
        Ok(None)
    };
    let single;
    let (mut head, refs, perturb_first): (Decoded, &[Ref], bool) = match &packet.0 {
        Body::RowPage(page, slot) => {
            let Some((head, source)) = page.decode_head(*slot) else {
                return reject();
            };
            single = source;
            (head, single.as_slice(), false)
        }
        Body::Typed(page, slot) => {
            let Some((head, source)) = page.head(*slot) else {
                return reject();
            };
            single = source;
            (head, single.as_slice(), false)
        }
        Body::MultiPage(page, slot) => {
            let p = &page.0;
            let Some(refs) = page.slice(*slot) else {
                return reject();
            };
            let Some(serial) = p.first_serial.checked_add(*slot as u64) else {
                return reject();
            };
            (
                Decoded {
                    serial,
                    origin: "multi",
                    run: p.run,
                    layout: p.layout.clone(),
                    template: p.template,
                    refs: Vec::new(),
                    ports: None,
                },
                refs,
                p.invalid_version,
            )
        }
        _ => return Err("expected an immutable source page".into()),
    };
    let rule = &graph.program.rules[rid];
    let (current, grouped, fused, audit) = STATE.with_borrow(|s| {
        let s = s.as_ref().unwrap();
        (
            s.layout
                .get(rid)
                .is_some_and(|l| Rc::ptr_eq(l, &head.layout)),
            s.lean & 4 != 0,
            s.lean & 16 != 0,
            s.audit,
        )
    });
    if !current
        || head.layout.rid != rid
        || head.template != rule.template
        || head.run != graph.epoch
    {
        return reject();
    }
    let mut covered = 0u64;
    let mut checks = 0u64;
    for (i, r) in refs.iter().enumerate() {
        let version = r.version.wrapping_add(u64::from(perturb_first && i == 0));
        let Some(atom) = rule.query.get(r.atom) else {
            return reject();
        };
        let Call::Table(t) = atom.call else {
            return reject();
        };
        if known(r.atom) != Some(r.row) {
            return reject();
        }
        let valid = if fused {
            graph.receipt_header(r.row) == Some((t, version))
        } else {
            graph.visible_epoch(r.row) == Some(version) && graph.live_table(r.row) == Some(t)
        };
        if !valid {
            return reject();
        }
        checks += 1;
        if grouped && r.atom < 64 {
            covered |= 1u64 << r.atom
        }
        if audit {
            head.refs.push(Ref {
                atom: r.atom,
                row: r.row,
                version,
            });
        }
    }
    let mut omitted = 0;
    let mut values = Slots::default();
    for f in &head.layout.fields {
        if let Some(table) = f.kind {
            if grouped && f.atom < 64 && covered & (1u64 << f.atom) != 0 {
                omitted += 1;
            } else {
                let Some(dep) = known(f.atom) else {
                    return reject();
                };
                let valid = if fused {
                    graph.receipt_header(dep).is_some_and(|(t, _)| t == table)
                } else {
                    graph.live_table(dep) == Some(table) && graph.visible_epoch(dep).is_some()
                };
                if !valid {
                    return reject();
                }
                checks += 1;
                if grouped && f.atom < 64 {
                    covered |= 1u64 << f.atom
                }
            }
        }
        let Some(v) = verified.get(&f.slot) else {
            return reject();
        };
        values.insert(f.slot, v.clone());
    }
    STATE.with_borrow_mut(|s| {
        let s = s.as_mut().unwrap();
        s.sealed += 1;
        s.header_checks += checks;
        if fused {
            s.lean_stats.fused_header_reads += checks;
        }
        if head.origin == "multi" {
            s.lean_stats.multi_binds += 1;
        } else {
            s.lean_stats.single_binds += 1;
        }
        s.lean_stats.projected_values += head.layout.fields.len() as u64;
        s.lean_stats.archived_refs += head.refs.len() as u64;
        s.lean_stats.produced_refs += refs.len() as u64;
        s.lean_stats.skipped_atom_checks += omitted;
    });
    Ok(Some(Rc::new(Bound {
        recipe: head,
        values: BoundValues::TakeOnce(RefCell::new(Some(values))),
    })))
}

#[derive(Clone, Debug)]
pub(crate) struct TypedPage(Rc<TypedPageData>);

#[derive(Debug)]
struct TypedPageData {
    first: u64,
    run: u64,
    layout: Rc<Layout>,
    template: usize,
    atom: Option<usize>,
    rows: Vec<(Option<Dependency>, u64)>,
    wrong_port: bool,
}

impl TypedPage {
    pub fn at(&self, slot: usize) -> Recipe {
        Recipe(Body::Typed(self.clone(), slot))
    }

    fn head(&self, slot: usize) -> Option<(Decoded, Option<Ref>)> {
        let p = &self.0;
        let &(dep, ver) = p.rows.get(slot)?;
        let dep = if p.wrong_port {
            Some(dep.unwrap_or(Dependency::Function(0)))
        } else {
            dep
        };
        let source = dep.map(|row| Ref {
            atom: p.atom.unwrap_or(usize::MAX),
            row,
            version: ver.wrapping_add(u64::from(p.wrong_port)),
        });
        Some((
            Decoded {
                serial: p.first.checked_add(slot as u64)?,
                origin: "single",
                run: p.run,
                layout: p.layout.clone(),
                template: p.template,
                refs: vec![],
                ports: None,
            },
            source,
        ))
    }

    fn decode(&self, slot: usize) -> Option<Decoded> {
        let (mut h, reference) = self.head(slot)?;
        h.refs.extend(reference);
        Some(h)
    }
}

pub(crate) fn use_typed_page() -> bool {
    STATE.with_borrow(|s| s.as_ref().is_some_and(|s| s.lean & 8 != 0))
}

fn fold_words<const N: usize>(hash: &mut u64, words: [u64; N]) {
    for w in words {
        *hash = (*hash ^ w).wrapping_mul(1099511628211);
    }
}

pub(crate) fn typed_page(
    run: u64,
    rid: usize,
    atom: Option<usize>,
    rows: Vec<(Option<Dependency>, u64)>,
) -> Option<TypedPage> {
    STATE.with_borrow_mut(|s| {
        let st = s.as_mut()?;
        if rows.is_empty() {
            return None;
        }
        let layout = st.layout.get(rid)?.clone();
        let first = st.serial.checked_add(1)?;
        let count = rows.len() as u64;
        let template = if st.mode == "wrong-template" {
            layout.template.wrapping_add(1)
        } else {
            layout.template
        };
        let wrong = st.mode == "wrong-port";
        let withheld = st.mode == "withhold";
        let audit_wire = st.audit && !withheld;
        if audit_wire {
            fold_words(
                &mut st.wire_hash,
                [
                    0x33524345,
                    first,
                    run,
                    rid as u64,
                    template as u64,
                    atom.map_or(u64::MAX, |v| v as u64),
                    1,
                    count,
                ],
            );
        }
        if st.record_fingerprint() {
            for (i, &(dep, ver)) in rows.iter().enumerate() {
                let (tag, id) = match dep {
                    Some(Dependency::Fact(f)) => (1, (u64::from(f.cell) << 32) | u64::from(f.op)),
                    Some(Dependency::Function(n)) => (2, n as u64),
                    None => (0, 0),
                };
                fold_words(
                    &mut st.raw,
                    [
                        first + i as u64,
                        run,
                        rid as u64,
                        layout.template as u64,
                        u64::from(dep.is_some()),
                    ],
                );
                if let Some(a) = atom
                    && dep.is_some()
                {
                    fold_words(&mut st.raw, [a as u64, tag, id, ver]);
                }
                if audit_wire {
                    fold_words(
                        &mut st.wire_hash,
                        [
                            if wrong && tag == 0 { 2 } else { tag },
                            id,
                            ver.wrapping_add(u64::from(wrong)),
                        ],
                    );
                }
            }
        } else {
            st.lean_stats.raw_omitted += count;
        }
        st.serial = st.serial.checked_add(count)?;
        st.emitted[0] += count;
        if withheld {
            return None;
        }
        st.lean_stats.typed_rows += count;
        st.lean_stats.wire_bytes_avoided += (8 + 3 * count) * 8;
        Some(TypedPage(Rc::new(TypedPageData {
            first,
            run,
            layout,
            template,
            atom,
            rows,
            wrong_port: wrong,
        })))
    })
}
