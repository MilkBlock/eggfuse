#[derive(Default, Serialize)]
struct LibraryStats {
    invocations: u64,
    selected: u64,
    switches: u64,
}
#[derive(Default)]
struct PageLibrary {
    members: Option<Vec<bool>>,
    current: Option<bool>,
    stats: LibraryStats,
}
pub fn install_page_library(value: Json) -> Result<()> {
    let mask: Vec<bool> = serde_json::from_value(value).map_err(|e| e.to_string())?;
    STORE.with_borrow_mut(|store| {
        let s = store.as_mut().ok_or("missing trained issuer")?;
        if mask.len() != s.plans.len()
            || s.premises.mode != 9
            || s.word_verifier.mode != 2
            || s.factor_stream
        {
            return Err("incompatible compiled page library".into());
        }
        s.library.members = Some(mask);
        Ok(())
    })
}
impl Store {
    fn apply_page_library(&mut self, rid: usize) -> Result<()> {
        let Some(mask) = &self.library.members else {
            return Ok(());
        };
        let selected = mask[rid];
        self.library.stats.invocations += 1;
        self.library.stats.selected += u64::from(selected);
        if self.library.current != Some(selected) {
            crate::joint_root::configure_factor(if selected { 2 } else { 0 }, false)?;
            self.premises.mode = if selected { 9 } else { 0 };
            self.word_verifier.mode = if selected { 2 } else { 0 };
            self.library.current = Some(selected);
            self.library.stats.switches += 1;
        }
        Ok(())
    }
}
