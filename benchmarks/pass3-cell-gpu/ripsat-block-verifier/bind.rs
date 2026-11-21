
// The sole pivot was physically read at release. Its version was checked
// again on the receiving snapshot. These slots are the output of that read.
pub(crate) fn bind_block(
    port: crate::strict_named::BlockPort,
    epoch: u64,
    slots: &Slots,
) -> Result<Rc<Bound>> {
    STATE.with_borrow_mut(|state| {
        let state = state.as_mut().ok_or("missing block receiver")?;
        let layout = state.layout.get(port.rid).ok_or("missing block layout")?.clone();
        let recipe = Decoded {
            strict_code: 0,
            serial: port.serial,
            origin: "single",
            run: epoch,
            template: layout.template,
            layout,
            refs: vec![Ref { atom: 0, row: port.witness, version: port.version }],
            ports: None,
        };
        state.sealed += 1;
        let values = if matches!(state.encoding, Encoding::CheckedSlots) {
            BoundValues::TakeOnce(RefCell::new(Some(slots.clone())))
        } else {
            BoundValues::Retained(slots.clone())
        };
        Ok(Rc::new(Bound { recipe, values }))
    })
}
