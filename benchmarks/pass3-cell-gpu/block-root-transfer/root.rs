#[derive(Default, Serialize)]
struct BlockBindStats {
    accepted: u64,
    checked_page_slots: u64,
    parent_headers_saved: u64,
    projected_headers_saved: u64,
    exact_buffers: u64,
    audit_headers: u64,
}
pub fn configure_block_bind(mode: u64) -> Result<()> {
    if !(1..=3).contains(&mode) {
        return Err("invalid checked block handoff".into());
    }
    crate::ordinary_witness::allow_block_handoff()?;
    STATE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing root issuer")?;
        if !matches!(s.encoding, Encoding::CheckedSlots) {
            return Err("block handoff requires checked input slots".into());
        }
        s.block_bind = mode as u8;
        Ok(())
    })
}
pub(crate) fn bind_completed_block(
    input: Option<Recipe>,
    proof: crate::ordinary_witness::CheckedBlock<'_>,
) -> Result<Option<Rc<Bound>>> {
    let Some(packet) = input else { return Ok(None) };
    let (g, rid, checked_page, checked_slot, known, slots) = proof.parts();
    let Body::MultiPage(page, slot) = &packet.0 else {
        return bind(Some(packet), g, rid, known, slots);
    };
    STATE.with_borrow_mut(|cell|{
        let s=cell.as_mut().ok_or("missing checked root state")?;
        let p=&page.0;
        // The body and the typed continuation must name the very same sealed
        // page and lane, not just an equal template or an equal e-class.
        let attested=if s.block_bind==3{checked_slot.wrapping_add(1)}else{checked_slot};
        if !Rc::ptr_eq(&page.0,&checked_page.0) || *slot!=attested{
            return Err("checked root handoff named a foreign page lane".into())
        }
        s.block_proofs.checked_page_slots+=1;
        if *slot>=p.count || p.invalid_version || p.withheld || p.run!=g.epoch || p.layout.rid!=rid
            || p.template!=g.program.rules[rid].template
            || !s.layout.get(rid).is_some_and(|l|Rc::ptr_eq(l,&p.layout)) {
            s.rejected+=1;return Ok(None)
        }
        let mut refs=Vec::new();
        if s.audit{
            let mut scratch=Vec::new();
            for r in page.read_parents(*slot,&mut scratch)?{
                if known.get(r.atom)!=Some(&Some(r.row)) || g.visible_epoch(r.row)!=Some(r.version)
                    || !matches!(g.program.rules[rid].query[r.atom].call,Call::Table(t) if g.live_table(r.row)==Some(t)){
                    return Err("checked block parent failed independent header audit".into())
                }
                s.block_proofs.audit_headers+=1;refs.push(r.clone());
            }
            for f in &p.layout.fields{
                if let Some(t)=f.kind{
                    let w=known.get(f.atom).copied().flatten().ok_or("missing certified field witness")?;
                    if g.live_table(w)!=Some(t) || g.visible_epoch(w).is_none(){return Err("invalid block field witness".into())}
                    s.block_proofs.audit_headers+=1;
                }
            }
        }
        let values=if s.block_bind==2 && p.layout.fields.len()==slots.len()
            && p.layout.fields.iter().zip(slots.iter()).all(|(f,(k,_))|f.slot==*k) {
            s.block_proofs.exact_buffers+=1;slots.clone()
        }else{
            let mut dst=Slots::default();
            for f in &p.layout.fields {let Some(value)=slots.get(&f.slot) else{s.rejected+=1;return Ok(None)};
                dst.insert(f.slot,value.clone());}
            dst
        };
        let recipe=Decoded{serial:p.first_serial.checked_add(*slot as u64).ok_or("page serial overflow")?,
            origin:"multi",run:p.run,layout:p.layout.clone(),template:p.template,refs,ports:None};
        s.block_proofs.accepted+=1;s.block_proofs.parent_headers_saved+=p.width as u64;
        s.block_proofs.projected_headers_saved+=p.layout.fields.iter().filter(|f|f.kind.is_some()).count() as u64;
        s.sealed+=1;
        Ok(Some(Rc::new(Bound{recipe,values:BoundValues::TakeOnce(RefCell::new(Some(values)))})))
    })
}
