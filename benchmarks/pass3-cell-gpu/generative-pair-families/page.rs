#[derive(Clone, Debug)]
struct FamilyRows {
    atoms: [usize; 2],
    rows: [Rc<Vec<(Dependency, u64)>>; 2],
    // These offsets exist only after the receiver regenerated and screened actual pairs.
    pairs: Vec<[u32; 2]>,
}
impl FamilyRows {
    fn at(&self, i: usize) -> [Ref; 2] {
        std::array::from_fn(|k| {
            let (row, version) = self.rows[k][self.pairs[i][k] as usize];
            Ref {
                atom: self.atoms[k],
                row,
                version,
            }
        })
    }
}
pub(crate) fn family_page(
    run: u64,
    rid: usize,
    atoms: [usize; 2],
    rows: [Rc<Vec<(Dependency, u64)>>; 2],
    pairs: Vec<[u32; 2]>,
) -> Result<MultiPage> {
    STATE.with_borrow_mut(|s| {
        let st = s.as_mut().ok_or("missing family receiver")?;
        let layout = st.layout.get(rid).ok_or("invalid family rule")?.clone();
        let count = pairs.len();
        let first_serial = st.serial.checked_add(1).ok_or("serial overflow")?;
        st.serial = st
            .serial
            .checked_add(count as u64)
            .ok_or("serial overflow")?;
        Ok(MultiPage(Rc::new(MultiPageData {
            seal: mint_local_seal(st.redemption != 0),
            run,
            first_serial,
            width: 2,
            count,
            template: layout.template,
            layout,
            refs: vec![],
            bucket: None,
            family: Some(FamilyRows { atoms, rows, pairs }),
            withheld: false,
            invalid_version: false,
        })))
    })
}
