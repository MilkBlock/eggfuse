/// The caller has just checked all parents and the complete suffix under one immutable graph borrow.
pub(crate) fn bind_checked_page(
    input: Option<Recipe>,
    g: &Graph,
    rid: usize,
    known: &[Option<Dependency>],
    slots: &Slots,
    defer_refs: bool,
    counts: &mut [u64; 4],
) -> Result<Option<Rc<Bound>>> {
    let Some(packet) = input else { return Ok(None) };
    let Body::MultiPage(page, slot) = &packet.0 else {
        return Err("page certificate expected".into());
    };
    let reject = || {
        STATE.with_borrow_mut(|s| s.as_mut().unwrap().rejected += 1);
        Ok(None)
    };
    let parents = page.parents(*slot);
    let borrowed = defer_refs;
    let recipe = if borrowed {
        let data = &page.0;
        let Some(serial) = data.first_serial.checked_add(*slot as u64) else {
            return reject();
        };
        if data.invalid_version {
            return reject();
        }
        Decoded {
            serial,
            origin: "multi",
            run: data.run,
            layout: data.layout.clone(),
            template: data.template,
            refs: ParentRefs::Page(page.clone(), *slot),
            ports: None,
        }
    } else {
        let Some(r) = decode(&packet) else {
            return reject();
        };
        r
    };
    let eligible = STATE.with_borrow(|s| {
        s.as_ref().is_some_and(|s| {
            matches!(s.encoding, Encoding::CheckedSlots)
                && s.layout
                    .get(rid)
                    .is_some_and(|current| Rc::ptr_eq(current, &recipe.layout))
        })
    });
    if !eligible {
        return Err("checked page requires current checked-slot layout".into());
    }

    if recipe.layout.rid != rid
        || recipe.template != g.program.rules[rid].template
        || recipe.run != g.epoch
        || (!borrowed && recipe.refs.len() != parents.len())
    {
        return reject();
    }
    if borrowed {
        for r in parents {
            if known.get(r.atom) != Some(&Some(r.row)) {
                return reject();
            }
        }
    } else {
        for (r, parent) in recipe.refs.iter().zip(parents) {
            if r.atom != parent.atom
                || r.row != parent.row
                || r.version != parent.version
                || known.get(r.atom) != Some(&Some(r.row))
            {
                return reject();
            }
        }
    }
    let mut values = Slots::default();
    let mut fields = 0;
    for field in &recipe.layout.fields {
        if field.kind.is_some() {
            if known.get(field.atom).is_none_or(|w| w.is_none()) {
                return reject();
            }
            fields += 1;
        }
        let Some(value) = slots.get(&field.slot) else {
            return reject();
        };
        values.insert(field.slot, value.clone());
    }
    counts[0] += 1;
    counts[3] += u64::from(borrowed) * parents.len() as u64;
    counts[1] += parents.len() as u64;
    counts[2] += fields;
    STATE.with_borrow_mut(|s| s.as_mut().unwrap().sealed += 1);
    Ok(Some(Rc::new(Bound {
        recipe,
        values: BoundValues::TakeOnce(RefCell::new(Some(values))),
    })))
}
