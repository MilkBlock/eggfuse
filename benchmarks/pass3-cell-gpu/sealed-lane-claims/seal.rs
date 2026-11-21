// This identity is minted inside the native issuer after the page's words are
// fixed. It is never taken from a model field, a source serial or wire bytes.
thread_local! {
    static NEXT_SEAL:std::cell::Cell<u64>=const{std::cell::Cell::new(0)};
}
fn mint_local_seal(enabled: bool) -> u64 {
    if !enabled {
        return 0;
    }
    NEXT_SEAL.with(|next| {
        let id = next
            .get()
            .checked_add(1)
            .expect("local page seal identity exhausted");
        next.set(id);
        id
    })
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct SealedLane {
    seal: u64,
    lane: usize,
}
impl Recipe {
    fn reissue(&self, sealed: bool) -> Option<Recipe> {
        match &self.0 {
            Body::RowPage(page, lane) => {
                let mut other = page.clone();
                other.seal = mint_local_seal(sealed);
                Some(other.at(*lane))
            }
            Body::MultiPage(page, lane) => {
                let mut other = (*page.0).clone();
                other.seal = mint_local_seal(sealed);
                MultiPage(Rc::new(other)).recipe(*lane)
            }
            _ => None,
        }
    }
    fn local_lane(&self) -> Option<SealedLane> {
        let (seal, lane) = match &self.0 {
            Body::RowPage(p, i) => (p.seal, *i),
            Body::MultiPage(p, i) => (p.0.seal, *i),
            _ => return None,
        };
        (seal != 0).then_some(SealedLane { seal, lane })
    }
}
#[derive(Default, Serialize)]
struct RedemptionStats {
    attempts: u64,
    fast_accepts: u64,
    fast_denials: u64,
    content_reads: u64,
    audit_comparisons: u64,
    reissued_denials: u64,
    missing_seals: u64,
}
pub fn configure_redemption(mode: u64) -> Result<()> {
    if mode > 3 {
        return Err("unsupported staged-parent attestation".into());
    }
    STATE.with_borrow_mut(|c| {
        let s = c.as_mut().ok_or("missing root state")?;
        if !s.stage_watch {
            return Err("sealed lane requires a staging parent".into());
        }
        s.redemption = mode as u8;
        Ok(())
    })
}
fn same_parents(offered: &Decoded, r: &Decoded) -> bool {
    offered.serial == r.serial
        && offered.origin == r.origin
        && offered.run == r.run
        && offered.template == r.template
        && Rc::ptr_eq(&offered.layout, &r.layout)
        && offered.refs.len() == r.refs.len()
        && offered
            .refs
            .iter()
            .zip(&r.refs)
            .all(|(a, b)| a.atom == b.atom && a.row == b.row && a.version == b.version)
}

pub(crate) fn same_staged_parent(recipe: &Recipe) -> bool {
    let (mode, audit, expected) = STATE.with_borrow(|c| {
        let Some(s) = c.as_ref() else {
            return (0, false, None);
        };
        (
            s.redemption,
            s.audit,
            s.stage_bound.as_ref().and_then(|b| b.lane),
        )
    });
    let reissued = (mode >= 2).then(|| recipe.reissue(mode == 2)).flatten();
    let candidate = reissued.as_ref().unwrap_or(recipe);
    let supplied = candidate.local_lane();
    if mode != 0
        && let (Some(a), Some(b)) = (supplied, expected)
    {
        let equal = a == b;
        // Decode OUTSIDE the STATE borrow; singleton decoding consults the source layout registry.
        let independent = if audit { decode(candidate) } else { None };
        return STATE.with_borrow_mut(|c| {
            let s = c.as_mut().unwrap();
            if audit {
                let old = independent
                    .as_ref()
                    .zip(s.stage_bound.as_ref())
                    .is_some_and(|(o, b)| same_parents(o, &b.recipe));
                if mode == 2 {
                    assert!(
                        old && !equal,
                        "reissued immutable payload must match contents and lose authority"
                    );
                } else {
                    assert_eq!(
                        old, equal,
                        "page identity disagrees with full parent validation"
                    );
                }
                s.redemption_stats.audit_comparisons += 1;
            }
            s.redemption_stats.attempts += 1;
            s.redemption_stats.fast_accepts += u64::from(equal);
            s.redemption_stats.fast_denials += u64::from(!equal);
            s.redemption_stats.reissued_denials += u64::from(mode == 2 && !equal);
            equal
        });
    }
    if mode != 0 {
        let same = if audit && mode == 3 {
            decode(candidate)
        } else {
            None
        };
        return STATE.with_borrow_mut(|c| {
            let st = c.as_mut().unwrap();
            if audit && mode == 3 {
                assert!(
                    same.as_ref()
                        .zip(st.stage_bound.as_ref())
                        .is_some_and(|(o, b)| same_parents(o, &b.recipe))
                );
                st.redemption_stats.audit_comparisons += 1;
            }
            st.redemption_stats.attempts += 1;
            st.redemption_stats.missing_seals += 1;
            st.redemption_stats.fast_denials += 1;
            false
        });
    }
    let decoded = decode(recipe);
    STATE.with_borrow_mut(|c| {
        let Some(s) = c.as_mut() else { return false };
        s.redemption_stats.attempts += 1;
        s.redemption_stats.content_reads += 1;
        decoded
            .as_ref()
            .zip(s.stage_bound.as_ref())
            .is_some_and(|(o, b)| same_parents(o, &b.recipe))
    })
}
