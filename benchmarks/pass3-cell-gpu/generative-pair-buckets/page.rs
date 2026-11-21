// The only per-parent list is the receiver's read-only public table index, shared
// across independent group packets. A packet contains neither this Rc nor its rows.
#[derive(Clone,Debug)]
struct VerifiedBucket {
    left: Ref,
    atom: usize,
    posting: Rc<Vec<(Dependency,u64)>>,
}
pub(crate) enum PageLane<'a>{External(&'a [Ref]),Generated([Ref;2])}
impl std::ops::Deref for PageLane<'_>{
    type Target=[Ref];
    fn deref(&self)->&[Ref]{match self{Self::External(r)=>r,Self::Generated(r)=>r}}
}
pub(crate) fn bucket_page(run:u64,rid:usize,left:Ref,atom:usize,posting:Rc<Vec<(Dependency,u64)>>)->Result<MultiPage>{
    STATE.with_borrow_mut(|s|{
        let st=s.as_mut().ok_or("missing bucket receiver")?;
        let layout=st.layout.get(rid).ok_or("invalid bucket rule")?.clone();
        let count=posting.len();if !(2..=64).contains(&count){return Err("invalid verified bucket size".into())}
        let first_serial=st.serial.checked_add(1).ok_or("serial overflow")?;
        st.serial=st.serial.checked_add(count as u64).ok_or("serial overflow")?;
        Ok(MultiPage(Rc::new(MultiPageData{seal:mint_local_seal(st.redemption!=0),run,first_serial,width:2,count,
            template:layout.template,layout,refs:vec![],bucket:Some(VerifiedBucket{left,atom,posting}),withheld:false,invalid_version:false})))
    })
}
