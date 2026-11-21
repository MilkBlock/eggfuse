#[derive(Default)]
struct WindowSurvey {
    width: usize,
    current: Option<([u64; 8], u64)>,
    // tuple: number of distinct prospective calls, generated root packets
    samples: std::collections::BTreeMap<([u64; 8], u64), u64>,
}
impl WindowSurvey {
    fn start(
        &mut self,
        c: &Context,
        rid: usize,
        steps: &[StackStep],
        pos: usize,
        len: usize,
        issued: u64,
    ) {
        let end = (pos + self.width).min(len);
        let f = &steps[0].frame;
        let fresh = f.rows[pos..end]
            .iter()
            .filter(|r| r.epoch >= c.watermark)
            .count();
        // All keys are known before the first recursive matcher call in this block.
        let sizes = |v: usize| {
            if v == 0 {
                0
            } else {
                usize::BITS as u64 - v.leading_zeros() as u64
            }
        };
        let x = [
            rid as u64,
            steps.len() as u64,
            (end - pos) as u64,
            fresh as u64,
            sizes(len),
            sizes(steps[1].frame.rows.len()),
            sizes(steps.last().unwrap().frame.rows.len()),
            u64::from(c.remaining[1] >= c.watermark),
        ];
        self.current = Some((x, issued));
    }
    fn finish(&mut self, issued: u64) {
        if let Some((x, start)) = self.current.take() {
            *self.samples.entry((x, issued - start)).or_default() += 1;
        }
    }
    fn report(&self) -> Json {
        json!({"width":self.width,"hist":self.samples.iter().map(|((x,y),n)|(x,*y,*n)).collect::<Vec<_>>()})
    }
}
pub fn window_survey(width: u64) -> Result<()> {
    if ![4, 16, 64, 256].contains(&width) {
        return Err("unsupported audit window".into());
    }
    STORE
        .with_borrow_mut(|s| {
            s.as_mut()
                .ok_or("no multi issuer")
                .map(|s| s.windows.width = width as usize)
        })
        .map_err(Into::into)
}
