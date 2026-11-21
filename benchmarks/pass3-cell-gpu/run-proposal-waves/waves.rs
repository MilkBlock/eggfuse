struct WaitingPageBank {
    epoch: u64,
    run: usize,
    watermark: u64,
    unions: u64,
    remaining: Vec<u64>,
    pages: Vec<crate::joint_root::MultiPage>,
    tuples: usize,
}
#[derive(Default, Serialize)]
struct WaveStats {
    waves: u64,
    multi_sets: u64,
    single_sets: u64,
    sealed_multi: u64,
    sealed_single: u64,
    peak_tuples: u64,
    peak_rules: u64,
    mixed_waves: u64,
    multiple_rules: u64,
    validated_multi_sets: u64,
    verified_single_sets: u64,
}
#[derive(Default)]
struct RunWave {
    width: usize,
    preparing: bool,
    waiting: HashMap<usize, WaitingPageBank>,
    stats: WaveStats,
    active_rules: u64,
    active_tuples: u64,
    singles: u64,
    multis: u64,
}
pub fn configure_run_wave(width: u64) -> Result<()> {
    if width == 0 || width > 65536 {
        return Err("invalid proposal wave width".into());
    }
    STORE.with_borrow_mut(|x| {
        let s = x.as_mut().ok_or("wave needs live parent issuer")?;
        if !s.page || s.residual || s.cap != usize::MAX {
            return Err("wave requires complete sealed parent pages".into());
        }
        s.wave.width = width as usize;
        Ok(())
    })
}
pub(crate) fn wave_width() -> usize {
    STORE.with_borrow(|x| x.as_ref().map_or(0, |s| s.wave.width))
}
pub(crate) fn wave_begin() -> Result<()> {
    STORE.with_borrow_mut(|x| {
        let w = &mut x.as_mut().ok_or("no wave state")?.wave;
        if !w.waiting.is_empty() {
            return Err("undrained multi-parent wave".into());
        }
        w.active_rules = 0;
        w.active_tuples = 0;
        w.singles = 0;
        w.multis = 0;
        Ok(())
    })
}
pub(crate) fn wave_mark(single: bool, n: usize) {
    STORE.with_borrow_mut(|x| {
        let w = &mut x.as_mut().unwrap().wave;
        w.active_rules += 1;
        w.active_tuples += n as u64;
        if single {
            w.singles += 1;
            w.stats.single_sets += 1;
            w.stats.sealed_single += n as u64;
        } else {
            w.multis += 1;
            w.stats.multi_sets += 1;
            w.stats.sealed_multi += n as u64;
        }
    })
}
pub(crate) fn wave_sealed() {
    STORE.with_borrow_mut(|x| {
        let w = &mut x.as_mut().unwrap().wave;
        w.stats.waves += 1;
        w.stats.peak_rules = w.stats.peak_rules.max(w.active_rules);
        w.stats.peak_tuples = w.stats.peak_tuples.max(w.active_tuples);
        w.stats.multiple_rules += u64::from(w.active_rules > 1);
        w.stats.mixed_waves += u64::from(w.singles > 0 && w.multis > 0);
    })
}
pub(crate) fn wave_single_consumed() {
    STORE.with_borrow_mut(|x| x.as_mut().unwrap().wave.stats.verified_single_sets += 1);
}
pub(crate) fn prepare_multi_wave(
    g: &Graph,
    rid: usize,
    run: usize,
    mark: u64,
    known: &QueryFacts,
) -> Result<()> {
    STORE.with_borrow_mut(|x| x.as_mut().unwrap().wave.preparing = true);
    let res = proposals(g, rid, run, mark, known);
    STORE.with_borrow_mut(|x| x.as_mut().unwrap().wave.preparing = false);
    let v = res?;
    if !v.is_empty() {
        return Err("multi-parent verified during issue wave".into());
    }
    let n = STORE
        .with_borrow(|x| x.as_ref().unwrap().wave.waiting.get(&rid).map(|p| p.tuples))
        .ok_or("unrecorded issue site")?;
    wave_mark(false, n);
    Ok(())
}
