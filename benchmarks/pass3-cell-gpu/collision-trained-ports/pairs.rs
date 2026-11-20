#[derive(Default)]
struct HardPairs {
    collect: bool,
    bins: BTreeMap<(u16, u16), u64>,
    omitted: u64,
    aliases: u64,
}
impl HardPairs {
    fn record(&mut self, l: &Value, r: &Value) {
        if !self.collect {
            return;
        }
        let a = mix(code_seed(l) ^ 0x8220e116bd89aae9) as u16;
        let b = mix(code_seed(r) ^ 0x8220e116bd89aae9) as u16;
        if a == b {
            self.aliases += 1;
            return;
        }
        let key = (a.min(b), a.max(b));
        if !self.bins.contains_key(&key) && self.bins.len() >= 32768 {
            self.omitted += 1;
            return;
        }
        *self.bins.entry(key).or_default() += 1;
    }
    fn report(&self) -> Json {
        if !self.collect {
            return Json::Null;
        }
        json!({"pairs":self.bins.iter().map(|(&(a,b),&n)|[a as u64,b as u64,n]).collect::<Vec<_>>(),
               "alias":self.aliases,"omitted":self.omitted})
    }
}
pub fn capture_collisions() -> Result<()> {
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("no source policy")?;
        if !s.detailed || !s.page || s.views != 1 {
            return Err("capture requires an audited single-view page run".into());
        }
        s.hard_pairs.collect = true;
        Ok(())
    })
}
pub fn use_secondary(weights: &[u8], codes: &[u8]) -> Result<()> {
    let m: Model = serde_json::from_slice(weights).map_err(|e| e.to_string())?;
    let table = BakedCodes::decode(codes, &m)?;
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("no source policy")?;
        if !s.packed_lookup
            || s.views != 2
            || s.radius != 0
            || s.mode != "learned"
            || !m
                .q
                .iter()
                .flatten()
                .zip(m.k.iter().flatten())
                .all(|(a, b)| a.is_finite() && a.to_bits() == b.to_bits())
        {
            return Err("secondary port projection requires a tied two-view policy".into());
        }
        s.secondary = Some(table);
        Ok(())
    })
}
