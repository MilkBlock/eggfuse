pub(crate) struct Selection {
    pub internal: Vec<bool>,
    pub spans: Vec<(bool, usize)>,
}
pub(crate) fn certify(
    epoch: u64,
    rid: usize,
    pivot: Option<usize>,
    sources: &[SourceHeader],
    scores: &[f32],
    dead: &[bool],
    wm: u64,
    first_model: u64,
    floor: f32,
) -> Result<Option<Selection>> {
    S.with_borrow_mut(|state| {
        let Some(s) = state else { return Ok(None) };
        let Some(pivot) = pivot else { return Ok(None) };
        if sources.is_empty() {
            return Ok(None);
        }
        s.counts.nonempty_banks += 1;
        let Some(mut bank) = s.collect.remove(&(rid, pivot)) else {
            s.counts.without_offer += 1;
            return Ok(None);
        };
        if sources
            .windows(2)
            .any(|pair| pair[0].source >= pair[1].source)
        {
            s.counts.order_version += 1;
            return Ok(None);
        }
        let mut slots = [None, None];
        let mut retained = Vec::new();
        let mut model_ids = Vec::new();
        let mut mask = vec![false; sources.len()];
        let mut spans: Vec<(bool, usize)> = Vec::new();
        let mut external = 0usize;
        let mut ambiguous = false;
        for (i, (h, &score)) in sources.iter().zip(scores).enumerate() {
            if score < floor || dead.get(i).copied().unwrap_or(false) {
                continue;
            }
            let hit = if let Some(w) = h.source {
                bank.remove(&w)
            } else {
                None
            };
            let private = match hit {
                Some(Some(lane)) if h.source == Some(lane.w) && h.version == lane.version => {
                    let gi = usize::from(h.version >= wm);
                    if slots[gi].is_some_and(|bits: u32| bits != score.to_bits()) {
                        s.counts.uncertified += 1;
                        return Ok(None);
                    }
                    slots[gi] = Some(score.to_bits());
                    model_ids.push(first_model + i as u64);
                    retained.push(lane);
                    mask[i] = true;
                    true
                }
                Some(_) => {
                    ambiguous = true;
                    false
                }
                None => false,
            };
            if !private {
                external += 1
            }
            if let Some((kind, len)) = spans.last_mut()
                && *kind == private
            {
                *len += 1
            } else {
                spans.push((private, 1))
            }
        }
        if ambiguous || !bank.is_empty() {
            s.counts.order_version += 1;
            return Ok(None);
        }
        if retained.is_empty() || (external > 0 && !s.partial) {
            s.counts.cardinality += 1;
            return Ok(None);
        }
        if external > 0 {
            s.counts.mixed_banks += 1;
            s.counts.mixed_lanes += retained.len() as u64;
            s.counts.external_in_mixed += external as u64;
            s.counts.external_spans +=
                spans.iter().filter(|(internal, _)| !*internal).count() as u64;
        } else {
            s.counts.closed_banks += 1;
            s.counts.closed_lanes += retained.len() as u64
        }
        s.counts.peak_bank = s.counts.peak_bank.max(retained.len());
        *s.closed_rules.entry(rid).or_default() += retained.len() as u64;
        assert!(
            s.ready
                .insert(
                    rid,
                    Closed {
                        pivot,
                        model_ids,
                        wire_ids: vec![],
                        scores: slots.map(|x| f32::from_bits(x.unwrap_or(0))),
                        lanes: retained,
                        ep: epoch,
                        wm
                    }
                )
                .is_none()
        );
        Ok(Some(Selection {
            internal: mask,
            spans,
        }))
    })
}
pub(crate) fn reserve_span(rid: usize, n: usize) -> Result<()> {
    let first = crate::joint_root::internal_serials(n)?;
    S.with_borrow_mut(|s| {
        s.as_mut()
            .unwrap()
            .ready
            .get_mut(&rid)
            .unwrap()
            .wire_ids
            .extend(first..first + n as u64)
    });
    Ok(())
}
pub fn set_partial(flag: bool) {
    S.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.partial = flag
        }
    })
}
